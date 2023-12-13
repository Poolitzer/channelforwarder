import logging
from typing import TypedDict, List, Literal, cast

from telegram import (
    Update,
    InputMediaVideo,
    InputMediaPhoto,
    InputMediaDocument,
    InputMediaAudio,
)
from telegram.ext import (
    MessageHandler,
    filters,
    ContextTypes,
    Defaults,
    PicklePersistence,
    ApplicationBuilder,
    Application,
)
from telegram.helpers import effective_message_type

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.ERROR,
    filename="log.log",
)

logger = logging.getLogger(__name__)

GROUP_ID = -100
CHANNEL_ID = -100
MEDIA_GROUP_TYPES = {
    "audio": InputMediaAudio,
    "document": InputMediaDocument,
    "photo": InputMediaPhoto,
    "video": InputMediaVideo,
}


class MsgDict(TypedDict):
    media_type: Literal["video", "photo"]
    media_id: str
    caption: str
    post_id: int


async def media_group_sender(context: ContextTypes.DEFAULT_TYPE):
    bot = context.bot
    context.job.data = cast(List[MsgDict], context.job.data)
    media = []
    for msg_dict in context.job.data:
        media.append(
            MEDIA_GROUP_TYPES[msg_dict["media_type"]](
                media=msg_dict["media_id"], caption=msg_dict["caption"]
            )
        )
    if not media:
        return
    msgs = await bot.send_media_group(chat_id=GROUP_ID, media=media)
    for index, msg in enumerate(msgs):
        context.bot_data["messages"][
            context.job.data[index]["post_id"]
        ] = msg.message_id
    await msgs[-1].pin()


async def new_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if message.media_group_id:
        media_type = effective_message_type(message)
        media_id = (
            message.photo[-1].file_id
            if message.photo
            else message.effective_attachment.file_id
        )
        msg_dict = {
            "media_type": media_type,
            "media_id": media_id,
            "caption": message.caption_html,
            "post_id": message.message_id,
        }
        jobs = context.job_queue.get_jobs_by_name(str(message.media_group_id))
        if jobs:
            jobs[0].data.append(msg_dict)
        else:
            context.job_queue.run_once(
                callback=media_group_sender,
                when=2,
                data=[msg_dict],
                name=str(message.media_group_id),
            )
    else:
        msg = await message.copy(chat_id=GROUP_ID)
        await context.bot.pin_chat_message(chat_id=GROUP_ID, message_id=msg.message_id)
        context.bot_data["messages"][message.message_id] = msg.message_id


async def edited_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    msg_id = context.bot_data["messages"][message.message_id]
    bot = context.bot
    if message.text:
        await bot.edit_message_text(
            chat_id=GROUP_ID, message_id=msg_id, text=message.text_html
        )
        return
    elif message.effective_attachment:
        media = None
        if message.location:
            await bot.edit_message_live_location(
                chat_id=GROUP_ID, message_id=msg_id, **message.location.to_dict()
            )
            return
        elif message.photo:
            media = InputMediaPhoto(
                media=message.photo[-1].file_id, caption=message.caption_html
            )
        elif message.video:
            media = InputMediaVideo(
                media=message.video.file_id, caption=message.caption_html
            )
        if not media:
            media = InputMediaDocument(
                media=message.effective_attachment.file_id, caption=message.caption_html
            )
        await bot.edit_message_media(chat_id=GROUP_ID, message_id=msg_id, media=media)


async def del_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == context.bot.id:
        await update.effective_message.delete()


async def post_init(application: Application):
    if "messages" not in application.bot_data:
        application.bot_data = {"messages": {}}


def main():
    pers = PicklePersistence("persistence")
    defaults = Defaults(parse_mode="HTML", disable_notification=True)
    application = (
        ApplicationBuilder()
        .token("BOTTOKEN")
        .persistence(pers)
        .defaults(defaults)
        .post_init(post_init)
        .build()
    )

    application.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST & filters.Chat(CHANNEL_ID), new_post
        )
    )
    application.add_handler(
        MessageHandler(
            filters.UpdateType.EDITED_CHANNEL_POST & filters.Chat(CHANNEL_ID),
            edited_post,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.StatusUpdate.PINNED_MESSAGE & filters.Chat(GROUP_ID), del_msg
        )
    )

    application.run_polling(
        allowed_updates=[
            Update.CHANNEL_POST,
            Update.EDITED_CHANNEL_POST,
            Update.MESSAGE,
        ]
    )


if __name__ == "__main__":
    main()

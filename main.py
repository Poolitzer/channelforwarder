from typing import TypedDict, List, Literal, cast

from telegram import Update, InputMediaVideo, InputMediaPhoto, InputMediaDocument, InputMediaAudio
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext, Defaults, PicklePersistence
from telegram.utils.helpers import effective_message_type
GROUP_ID = -100
CHANNEL_ID = -100
MEDIA_GROUP_TYPES = {"audio": InputMediaAudio, "document": InputMediaDocument, "photo": InputMediaPhoto,
                     "video": InputMediaVideo}


class MsgDict(TypedDict):
    media_type: Literal["video", "photo"]
    media_id: str
    caption: str
    post_id: int


def media_group_sender(context: CallbackContext):
    bot = context.bot
    context.job.context = cast(List[MsgDict], context.job.context)
    media = []
    for msg_dict in context.job.context:
        media.append(MEDIA_GROUP_TYPES[msg_dict["media_type"]](media=msg_dict["media_id"], caption=msg_dict["caption"]))
    if not media:
        return
    msgs = bot.send_media_group(chat_id=GROUP_ID, media=media)
    for index, msg in enumerate(msgs):
        context.bot_data["messages"][context.job.context[index]["post_id"]] = msg.message_id
    msgs[-1].pin()


def new_post(update: Update, context: CallbackContext):
    message = update.effective_message
    if message.media_group_id:
        media_type = effective_message_type(message)
        media_id = message.photo[-1].file_id if message.photo else message.effective_attachment.file_id
        msg_dict = {"media_type": media_type, "media_id": media_id, "caption": message.caption_html,
                    "post_id": message.message_id}
        jobs = context.job_queue.get_jobs_by_name(str(message.media_group_id))
        if jobs:
            jobs[0].context.append(msg_dict)
        else:
            context.job_queue.run_once(callback=media_group_sender, when=2, context=[msg_dict],
                                       name=str(message.media_group_id))
        return
    msg = message.copy(chat_id=GROUP_ID)
    context.bot.pin_chat_message(chat_id=GROUP_ID, message_id=msg.message_id)
    context.bot_data["messages"][message.message_id] = msg.message_id


def edited_post(update: Update, context: CallbackContext):
    message = update.effective_message
    msg_id = context.bot_data["messages"][message.message_id]
    bot = context.bot
    if message.text:
        bot.edit_message_text(chat_id=GROUP_ID, message_id=msg_id, text=message.text_html)
        return
    elif message.effective_attachment:
        media = None
        if message.location:
            bot.edit_message_live_location(chat_id=GROUP_ID, message_id=msg_id, **message.location.to_dict())
            return
        elif message.photo:
            media = InputMediaPhoto(media=message.photo[-1].file_id, caption=message.caption_html)
        elif message.video:
            media = InputMediaVideo(media=message.video.file_id, caption=message.caption_html)
        if not media:
            media = InputMediaDocument(media=message.effective_attachment.file_id, caption=message.caption_html)
        bot.edit_message_media(chat_id=GROUP_ID, message_id=msg_id, media=media)


def del_msg(update: Update, context: CallbackContext):
    if update.effective_user.id == context.bot.id:
        update.effective_message.delete()


def main():
    pers = PicklePersistence("persistence")
    defaults = Defaults(parse_mode="HTML", disable_notification=True)
    updater = Updater("BOTTOKEN", defaults=defaults, persistence=pers)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.update.channel_post & Filters.chat(CHANNEL_ID), new_post))
    dp.add_handler(MessageHandler(Filters.update.edited_channel_post & Filters.chat(CHANNEL_ID), edited_post))
    dp.add_handler(MessageHandler(Filters.status_update.pinned_message & Filters.chat(GROUP_ID), del_msg))
    if "messages" not in dp.bot_data:
        dp.bot_data = {"messages": {}}
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()

from pathlib import Path

path = Path("bot.js")
src = path.read_text()

start_marker = '    // GROUP_STATUS_COMMANDS_V1: separate from .antistatus.'
end_marker = '    if (command === "delgcstatus") {'

start = src.find(start_marker)
end = src.find(end_marker, start + 1)

if start < 0 or end < 0:
    raise SystemExit("ERROR: Could not locate the groupstatus block. No changes made.")

new_block = r'''    // GROUP_STATUS_COMMANDS_V1: separate from .antistatus.
    if (command === "groupstatus" || command === "gs") {
      if (!isAdmin) {
        await sock.sendMessage(message.key.remoteJid, {
          text: "Only group admins can post a group status."
        }, { quoted: message });
        return;
      }

      try {
        // Unwrap common WhatsApp message containers safely.
        function unwrapStatusMessage(msg) {
          let current = msg || {};
          for (let i = 0; i < 8; i++) {
            const next =
              current.ephemeralMessage?.message ||
              current.viewOnceMessage?.message ||
              current.viewOnceMessageV2?.message ||
              current.viewOnceMessageV2Extension?.message ||
              current.documentWithCaptionMessage?.message;
            if (!next || next === current) break;
            current = next;
          }
          return current;
        }

        const original = message.message || {};
        const currentMessage = unwrapStatusMessage(original);

        // Find the quoted message context, including wrapped commands.
        let contextInfo =
          currentMessage.extendedTextMessage?.contextInfo ||
          currentMessage.imageMessage?.contextInfo ||
          currentMessage.videoMessage?.contextInfo ||
          currentMessage.documentMessage?.contextInfo ||
          original.extendedTextMessage?.contextInfo ||
          {};

        const quotedMessage = unwrapStatusMessage(
          contextInfo.quotedMessage || {}
        );

        const commandText = args.join(" ").trim();

        const imageMsg =
          currentMessage.imageMessage || quotedMessage.imageMessage;
        const videoMsg =
          currentMessage.videoMessage || quotedMessage.videoMessage;

        const quotedText =
          quotedMessage.conversation ||
          quotedMessage.extendedTextMessage?.text ||
          quotedMessage.imageMessage?.caption ||
          quotedMessage.videoMessage?.caption ||
          quotedMessage.documentMessage?.caption ||
          "";

        const caption = commandText || quotedText.trim();

        let content;

        if (imageMsg || videoMsg) {
          let buffer;

          // Download the media from the message that actually contains it.
          if (currentMessage.imageMessage || currentMessage.videoMessage) {
            buffer = await downloadMediaMessage(
              message,
              "buffer",
              {},
              {
                logger: pino({ level: "silent" }),
                reuploadRequest: sock.updateMediaMessage
              }
            );
          } else {
            const mediaType = imageMsg ? "image" : "video";
            const stream = await downloadContentFromMessage(
              imageMsg || videoMsg,
              mediaType
            );
            const chunks = [];
            for await (const chunk of stream) chunks.push(chunk);
            buffer = Buffer.concat(chunks);
          }

          if (!buffer || buffer.length === 0) {
            throw new Error("Media download returned an empty buffer.");
          }

          content = imageMsg
            ? { image: buffer, caption }
            : { video: buffer, caption };
        } else {
          if (!caption) {
            await sock.sendMessage(message.key.remoteJid, {
              text: "Usage: .groupstatus Your status text\nOr reply to a text/image/video with .groupstatus, or caption your media with the command."
            }, { quoted: message });
            return;
          }

          content = {
            text: caption,
            backgroundColor: "#673AB7"
          };
        }

        const generated = await generateWAMessageContent(
          content,
          { upload: sock.waUploadToServer }
        );

        // Mark the inner media payload as a group status.
        if (generated.imageMessage) {
          generated.imageMessage.contextInfo = {
            ...(generated.imageMessage.contextInfo || {}),
            isGroupStatus: true
          };
        }
        if (generated.videoMessage) {
          generated.videoMessage.contextInfo = {
            ...(generated.videoMessage.contextInfo || {}),
            isGroupStatus: true
          };
        }

        const secret = crypto.randomBytes(32);

        const statusMessage = generateWAMessageFromContent(
          message.key.remoteJid,
          {
            messageContextInfo: { messageSecret: secret },
            groupStatusMessageV2: {
              message: {
                ...generated,
                messageContextInfo: { messageSecret: secret }
              }
            }
          },
          {}
        );

        await sock.relayMessage(
          message.key.remoteJid,
          statusMessage.message,
          { messageId: statusMessage.key.id }
        );

        groupStatusTracker.recordFromMessage(statusMessage);

        await sock.sendMessage(message.key.remoteJid, {
          text: "Status message sent to WhatsApp. Please check the group status to confirm it appeared."
        }, { quoted: message });
      } catch (err) {
        console.error("Group-status post failed:", err);
        await sock.sendMessage(message.key.remoteJid, {
          text: "I couldn't post that group status. Check the Railway logs for the error."
        }, { quoted: message });
      }
      return;
    }

'''

path.write_text(src[:start] + new_block + src[end:])
print("Patched only the groupstatus command block.")

/**
 * Tracks group-status message keys for up to 24 hours.
 * WhatsApp does not expose a reliable list of every status, so only statuses
 * observed while Silver is online (or posted by Silver itself) are tracked.
 */
const fs = require("fs");
const path = require("path");

const FILE = path.join(__dirname, "database", "groupStatuses.json");
const TTL_MS = 24 * 60 * 60 * 1000;
let data = {};

function unwrap(message) {
  let current = message;
  for (let i = 0; i < 6 && current; i++) {
    const inner =
      current.ephemeralMessage?.message ||
      current.deviceSentMessage?.message ||
      current.viewOnceMessage?.message ||
      current.viewOnceMessageV2?.message ||
      current.viewOnceMessageV2Extension?.message ||
      current.documentWithCaptionMessage?.message;
    if (!inner) break;
    current = inner;
  }
  return current;
}

function isGroupStatusMessage(message) {
  const value = unwrap(message);
  return Boolean(value?.groupStatusMessage || value?.groupStatusMessageV2);
}

function prune() {
  const cutoff = Date.now() - TTL_MS;
  for (const jid of Object.keys(data)) {
    data[jid] = (data[jid] || []).filter(item => item.ts >= cutoff);
    if (!data[jid].length) delete data[jid];
  }
}

function save() {
  try {
    fs.mkdirSync(path.dirname(FILE), { recursive: true });
    fs.writeFileSync(FILE, JSON.stringify(data, null, 2), "utf8");
  } catch (error) {
    console.error("[group-status-tracker] save failed:", error.message);
  }
}

function load() {
  try {
    if (fs.existsSync(FILE)) {
      data = JSON.parse(fs.readFileSync(FILE, "utf8")) || {};
    }
  } catch (error) {
    console.error("[group-status-tracker] load failed:", error.message);
    data = {};
  }
  prune();
}

function record(key, timestamp) {
  const jid = key?.remoteJid;
  if (!jid?.endsWith("@g.us") || !key?.id) return;

  const seconds =
    typeof timestamp?.toNumber === "function"
      ? timestamp.toNumber()
      : Number(timestamp);
  const ts = seconds > 0 ? seconds * 1000 : Date.now();
  if (Date.now() - ts > TTL_MS) return;

  const list = data[jid] || (data[jid] = []);
  if (list.some(item => item.key.id === key.id)) return;

  list.push({
    key: {
      remoteJid: jid,
      id: key.id,
      fromMe: Boolean(key.fromMe),
      ...(key.participant ? { participant: key.participant } : {})
    },
    ts
  });
  save();
}

function recordFromMessage(message) {
  if (!message?.key || !isGroupStatusMessage(message.message)) return;
  record(message.key, message.messageTimestamp);
}

function list(jid) {
  prune();
  return [...(data[jid] || [])];
}

function remove(jid, ids) {
  if (!data[jid]) return;
  const removed = new Set(ids || []);
  data[jid] = data[jid].filter(item => !removed.has(item.key.id));
  if (!data[jid].length) delete data[jid];
  save();
}

load();
module.exports = { isGroupStatusMessage, record, recordFromMessage, list, remove };

"use strict";

const byId = id => document.getElementById(id);
const transcript = byId("transcript");
const question = byId("question");
const searchInput = byId("policy-query");
const policyList = byId("policy-list");
const policyDialog = byId("policy-dialog");
const welcome = byId("welcome");
const documents = new Map();
let context = {};
let sending = false;
let searchRequest = 0;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

async function request(path, options) {
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Request failed.");
  return result;
}

function openPolicy(id, selectedClause) {
  const policy = documents.get(id);
  if (!policy) return;
  byId("policy-version").textContent = policy.id + " / VERSION " + policy.version;
  byId("policy-title").textContent = policy.title;
  const body = byId("policy-body");
  body.replaceChildren();
  for (const clause of policy.sections) {
    const section = element("section");
    section.id = "clause-" + clause.id;
    section.append(element("h3", "", clause.id + " · " + clause.title), element("p", "", clause.text));
    body.append(section);
  }
  policyDialog.showModal();
  if (selectedClause) byId("clause-" + selectedClause)?.scrollIntoView({block: "nearest"});
}

function libraryItem(policy, clause) {
  const button = element("button", "policy-link");
  button.type = "button";
  button.append(
    element("small", "", (clause ? clause.id : policy.id) + " / V" + policy.version),
    element("strong", "", clause ? clause.title : policy.title),
    element("span", "", clause ? clause.text : policy.sections.map(section => section.title).join(" · "))
  );
  button.addEventListener("click", () => openPolicy(policy.id, clause?.id));
  return button;
}

function showLibrary() {
  policyList.replaceChildren(...Array.from(documents.values(), policy => libraryItem(policy)));
}

byId("search-form").addEventListener("submit", async event => {
  event.preventDefault();
  const id = ++searchRequest;
  const query = searchInput.value.trim();
  if (!query) return showLibrary();
  try {
    const {results} = await request("/api/search?q=" + encodeURIComponent(query));
    if (id !== searchRequest) return;
    policyList.replaceChildren(...results.map(clause => libraryItem(documents.get(clause.document), clause)));
    if (!results.length) policyList.append(element("p", "", "No matching clauses. Try another keyword."));
  } catch {
    if (id === searchRequest) policyList.replaceChildren(element("p", "", "Policy search is unavailable. Try again."));
  }
});
searchInput.addEventListener("search", () => {
  if (!searchInput.value) {
    searchRequest++;
    showLibrary();
  }
});

const labels = {
  policy: "POLICY", clarify: "MORE DETAIL NEEDED", eligible: "ELIGIBLE",
  review: "RETURN REVIEW", order: "ORDER STATUS", handoff: "HANDOFF"
};

function appendMessage(role, text, result) {
  welcome.remove();
  const article = element("article", "message " + role);
  article.append(element("span", "message-label", role === "user" ? "YOU" : (labels[result?.kind] || "ASSISTANT")));
  article.append(element("p", "", text));
  if (result?.order) {
    const order = result.order;
    const card = element("div", "order-card");
    card.append(element("strong", "", order.id), element("span", "", order.item),
                element("span", "", order.channel), element("span", "", order.status));
    article.append(card);
  }
  if (result?.citations?.length) {
    const group = element("div", "citations");
    for (const clause of result.citations) {
      const cite = element("button", "cite", clause.id + " · " + clause.title);
      cite.type = "button";
      cite.addEventListener("click", () => openPolicy(clause.document, clause.id));
      group.append(cite);
    }
    article.append(group);
  }
  if (result?.handoff) {
    const h = result.handoff;
    if (h.action === "remote_chat") {
      const connect = element("button", "remote-connect");
      connect.type = "button";
      connect.append("Contact remote office", element("span", "", " ↗"));
      connect.addEventListener("click", () => openRemoteChat({
        reason: h.reason,
        store: h.store,
        order: h.order,
        question: result.question || text
      }));
      article.append(connect);
    } else {
      const copy = element("button", "quiet handoff", "Copy summary for store lead");
      copy.type = "button";
      copy.addEventListener("click", async () => {
        const summary = [h.store, h.order, h.reason, h.policy.join(", "), h.next_step].filter(Boolean).join("\n");
        try {
          await navigator.clipboard.writeText(summary);
          copy.textContent = "Summary copied";
        } catch {
          article.append(element("p", "", summary));
          copy.remove();
        }
      });
      article.append(copy);
    }
  }
  transcript.append(article);
  transcript.scrollTop = transcript.scrollHeight;
}

const remoteChat = byId("remote-chat");
const remoteLog = byId("remote-log");
const remoteStatus = byId("remote-status");
const remoteInput = byId("remote-input");
let remoteTimer = 0;

function remoteBubble(role, label, text) {
  const bubble = element("div", "remote-bubble " + role);
  bubble.append(element("small", "", label), document.createTextNode(text));
  remoteLog.append(bubble);
  remoteLog.scrollTop = remoteLog.scrollHeight;
}

function openRemoteChat(payload) {
  clearTimeout(remoteTimer);
  remoteChat.hidden = false;
  remoteStatus.textContent = "CONNECTING…";
  remoteStatus.classList.remove("online");
  remoteLog.replaceChildren();
  remoteBubble("store", "STORE " + (payload.store || "014").replace("STORE-", ""),
    payload.question || "This request needs a remote office review.");
  remoteTimer = setTimeout(() => {
    remoteStatus.textContent = "Online · Remote office";
    remoteStatus.classList.add("online");
    remoteBubble(
      "office",
      "REMOTE OFFICE",
      "This is the remote office. I can see the handoff from " +
        (payload.store || "the store") +
        ". Tell me what the customer needs, and I will confirm the next step."
    );
    remoteInput.focus();
  }, 700);
}

byId("remote-close").addEventListener("click", () => {
  clearTimeout(remoteTimer);
  remoteChat.hidden = true;
});

byId("remote-form").addEventListener("submit", event => {
  event.preventDefault();
  const text = remoteInput.value.trim();
  if (!text) return;
  remoteInput.value = "";
  remoteBubble("store", "YOU", text);
  clearTimeout(remoteTimer);
  remoteTimer = setTimeout(() => {
    remoteBubble(
      "office",
      "OFFICE",
      "Thanks. I have logged this with the remote office. Stay with the customer, and I will reply here with the confirmed guidance."
    );
  }, 650);
});

byId("chat-form").addEventListener("submit", async event => {
  event.preventDefault();
  const message = question.value.trim();
  if (!message || sending) return;
  sending = true;
  byId("send").disabled = true;
  byId("reset").disabled = true;
  appendMessage("user", message);
  question.value = "";
  const waiting = element("p", "message-label", "Looking this up…");
  transcript.append(waiting);
  transcript.scrollTop = transcript.scrollHeight;
  try {
    const result = await request("/api/chat", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message, context})
    });
    context = result.context;
    waiting.remove();
    result.question = message;
    appendMessage("assistant", result.text, result);
    byId("mode").textContent = result.engine + " · Sample data only.";
  } catch {
    waiting.remove();
    appendMessage("assistant", "Something went wrong. Please try again.");
  } finally {
    sending = false;
    byId("send").disabled = false;
    byId("reset").disabled = false;
    question.focus();
  }
});

byId("reset").addEventListener("click", () => {
  context = {};
  transcript.replaceChildren(welcome);
  question.value = "";
  question.focus();
});
document.querySelectorAll("[data-prompt]").forEach(button => {
  button.addEventListener("click", () => {
    question.value = button.dataset.prompt;
    question.focus();
    byId("chat-form").requestSubmit();
  });
});
request("/api/policies").then(({policies, store, openai}) => {
  for (const policy of policies) documents.set(policy.id, policy);
  byId("store").textContent = store.replace("STORE-", "Store ");
  byId("mode").textContent = (openai ? "Model enabled" : "Local rules") + " · Sample data only.";
  const count = document.querySelector(".library .count");
  if (count) {
    count.textContent = String(policies.length).padStart(2, "0") + " DOCS";
  }
  showLibrary();
}).catch(() => policyList.replaceChildren(element("p", "", "The policy library is unavailable.")));

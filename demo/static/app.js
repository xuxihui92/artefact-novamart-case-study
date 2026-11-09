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
    if (!results.length) policyList.append(element("p", "", "No matching clauses. Try a different keyword."));
  } catch {
    if (id === searchRequest) policyList.replaceChildren(element("p", "", "Policy search is unavailable."));
  }
});
searchInput.addEventListener("search", () => {
  if (!searchInput.value) {
    searchRequest++;
    showLibrary();
  }
});

const labels = {
  policy: "POLICY GUIDANCE", clarify: "NEEDS A DETAIL", eligible: "WITHIN RETURN WINDOW",
  review: "RETURN CHECK", order: "ORDER TOOL", handoff: "OPERATIONS HANDOFF"
};

function appendMessage(role, text, result) {
  welcome.remove();
  const article = element("article", "message " + role);
  article.append(element("span", "message-label", role === "user" ? "YOU" : (labels[result?.kind] || "RETURN DESK")));
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
    const copy = element("button", "quiet handoff", "Copy handoff summary");
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
  transcript.append(article);
  transcript.scrollTop = transcript.scrollHeight;
}

byId("chat-form").addEventListener("submit", async event => {
  event.preventDefault();
  const message = question.value.trim();
  if (!message || sending) return;
  sending = true;
  byId("send").disabled = true;
  byId("reset").disabled = true;
  appendMessage("user", message);
  question.value = "";
  const waiting = element("p", "message-label", "Checking…");
  transcript.append(waiting);
  transcript.scrollTop = transcript.scrollHeight;
  try {
    const result = await request("/api/chat", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message, context})
    });
    context = result.context;
    waiting.remove();
    appendMessage("assistant", result.text, result);
    byId("mode").textContent = result.engine + " · Use fictional details only.";
  } catch {
    waiting.remove();
    appendMessage("assistant", "The local service could not complete the request. Please try again.");
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
  byId("mode").textContent = (openai ? "OpenAI routing enabled" : "Local rules") + " · Use fictional details only.";
  showLibrary();
}).catch(() => policyList.replaceChildren(element("p", "", "Policy library is unavailable.")));

// Household intake: a short Q&A that tailors every answer. Saved only on this Mac, in household.json.
const hhDlg = $("#hh"), hhBody = $("#hhBody");
let hh = null, hhSteps = [], hhAt = 0;

const HOME_Q = [
  ["setting", "What kind of place do you live in?", "select", ["", "Rural", "Small town", "Suburban", "City"]],
  ["location", "Anything about your location that matters in an emergency?", "area", "Example: end of a 2-mile dirt road, one way out, nearest hospital 45 minutes away"],
  ["water", "Where does your water come from? How much do you store?", "area", "Example: private well with an electric pump; 30 gallons stored"],
  ["heat", "How do you heat your home and cook?", "area", "Example: propane furnace, wood stove, camp stove"],
  ["power", "What backup power do you have?", "area", "Example: 5 kW gasoline generator, no transfer switch"],
  ["supplies", "What medical and emergency supplies do you keep?", "area", "Example: trauma kit with tourniquet, 2 EpiPens, N95 masks, fire extinguisher"],
];
const PERSON_Q = [
  ["name", "Name or nickname", "text", "The name you will use in questions, like \"Sam\" or \"Grandpa\""],
  ["born", "Birth year", "text", "Example: 1984. For babies, add the month: 2025-03"],
  ["sex", "Sex", "select", ["", "female", "male", "other"]],
  ["weight", "Weight", "text", "Example: 165 lb or 20 kg. Children's doses often go by weight."],
  ["pregnant", "Pregnant or breastfeeding?", "select", ["", "Pregnant", "Breastfeeding"]],
  ["conditions", "Health conditions", "area", "Example: asthma, type 1 diabetes, heart disease, seizures"],
  ["medications", "Daily medicines, with doses", "area", "Example: insulin glargine 20 units at night; lisinopril 10 mg each morning"],
  ["allergies", "Allergies, and what happens", "area", "Example: penicillin, hives; bee stings, anaphylaxis, carries an EpiPen"],
  ["blood_type", "Blood type, if known", "text", "Example: O+"],
  ["mobility", "Mobility, vision, hearing, or other needs", "area", "Example: uses a walker; hearing aids; sleeps with a CPAP"],
  ["skills", "First aid or other training", "area", "Example: CPR certified, EMT, wilderness first aid, ham radio license"],
  ["notes", "Anything else a medic should know", "area", "Example: pacemaker, past surgeries, contact lenses"],
];

function hhField([k, label, type, extra], val) {
  val = val || "";
  let input;
  if (type === "select") {
    input = `<select data-k="${k}">${extra.map((o) => `<option value="${o}"${o === val ? " selected" : ""}>${o || "—"}</option>`).join("")}</select>`;
  } else if (type === "area") {
    input = `<textarea data-k="${k}" rows="2">${esc(val)}</textarea>`;
  } else {
    input = `<input data-k="${k}" value="${esc(val)}">`;
  }
  const hint = type === "select" ? "" : `<small>${esc(extra)}</small>`;
  return `<label class="q"><span>${esc(label)}</span>${input}${hint}</label>`;
}

function hhAge(born) {
  const m = /^\s*(\d{4})(?:-(\d{1,2}))?/.exec(born || "");
  if (!m) return "";
  const now = new Date();
  const months = (now.getFullYear() - +m[1]) * 12 + now.getMonth() + 1 - +(m[2] || 7);
  if (months < 0) return "";
  return months < 24 ? `${months} months` : `${Math.floor(months / 12)} years`;
}

function hhBuild() {
  if (!hh.people.length) hh.people.push({});
  hhSteps = [{ kind: "intro" }, { kind: "home" }, ...hh.people.map((_, i) => ({ kind: "person", i })),
    { kind: "pets" }, { kind: "review" }];
}

function hhCollect() {
  const st = hhSteps[hhAt];
  const target = st.kind === "home" ? hh.home : st.kind === "person" ? hh.people[st.i] : null;
  hhBody.querySelectorAll("[data-k]").forEach((el) => {
    if (st.kind === "pets") hh.pets = el.value.trim();
    else if (target) target[el.dataset.k] = el.value.trim();
  });
}

function hhRender() {
  const st = hhSteps[hhAt], title = $("#hhTitle"), next = $("#hhNext");
  $("#hhStep").textContent = st.kind === "intro" ? "" : `Step ${hhAt} of ${hhSteps.length - 1}`;
  $("#hhBack").textContent = hhAt === 0 ? "Not now" : "Back";
  $("#hhAdd").hidden = st.kind !== "person";
  next.textContent = st.kind === "intro" ? "Start" : st.kind === "review" ? "Save" : "Next";
  if (st.kind === "intro") {
    title.textContent = "Tailor answers to your household";
    hhBody.innerHTML = `
      <p class="lead">A few questions about the people you live with and your home. Lifeboat then uses
        each person's age and weight, checks every treatment against their allergies and medicines,
        and fits advice to your water, heat, and power.</p>
      <p class="privacy"><b>Private.</b> Your answers are saved only on this Mac, in <code>household.json</code>.
        They never go into git and never leave this laptop. Skip any question. Change it any time with
        the <b>Household</b> button.</p>
      <p class="lead">It takes about 2 minutes per person.</p>`;
  } else if (st.kind === "home") {
    title.textContent = "Your home";
    hhBody.innerHTML = `<p class="lead">Skip anything you don't know.</p>` +
      HOME_Q.map((q) => hhField(q, hh.home[q[0]])).join("");
  } else if (st.kind === "person") {
    const p = hh.people[st.i];
    title.textContent = p.name ? p.name : `Person ${st.i + 1}`;
    const f = (k) => hhField(PERSON_Q.find((q) => q[0] === k), p[k]);
    hhBody.innerHTML = `<p class="lead">${st.i === 0 ? "Start with yourself." : "Skip anything you don't know."}</p>
      <div class="q2">${f("name")}${f("born")}${f("sex")}${f("weight")}</div>` +
      ["pregnant", "conditions", "medications", "allergies", "blood_type", "mobility", "skills", "notes"].map(f).join("") +
      (hh.people.length > 1 ? `<button type="button" class="link" id="hhRemove">Remove this person</button>` : "");
    $("#hhRemove")?.addEventListener("click", () => {
      hh.people.splice(st.i, 1); hhBuild(); hhAt = Math.min(hhAt, hhSteps.length - 1); hhRender();
    });
  } else if (st.kind === "pets") {
    title.textContent = "Pets";
    hhBody.innerHTML = hhField(["pets", "Do you have pets? Species, size, and any health needs.", "area",
      "Example: 2 dogs (70 lb lab, 12 lb terrier on thyroid pills); 6 chickens"], hh.pets);
  } else {
    title.textContent = "Check and save";
    const people = hh.people.filter((p) => p.name);
    const item = (p) => {
      const bits = [hhAge(p.born), p.sex, p.weight, p.pregnant].filter(Boolean).join(", ");
      const more = [["Conditions", p.conditions], ["Medicines", p.medications], ["Allergies", p.allergies]]
        .filter((x) => x[1]).map(([k, v]) => `<br><small>${k}: ${esc(v)}</small>`).join("");
      return `<li><b>${esc(p.name)}</b>${bits ? " · " + esc(bits) : ""}${more}</li>`;
    };
    const unnamed = hh.people.length - people.length;
    hhBody.innerHTML = `<p class="lead">Lifeboat will use this in every answer. Go back to change anything.</p>
      <ul class="hh-review">${people.map(item).join("") || "<li>No people yet.</li>"}</ul>
      ${unnamed ? `<p class="err">${unnamed} person without a name will be left out. Go back and add a name.</p>` : ""}
      <p class="lead">Home: ${Object.values(hh.home).filter(Boolean).length} answers · Pets: ${hh.pets ? "yes" : "none"}</p>`;
  }
  (hhBody.querySelector("input, textarea, select") || next).focus();
}

async function openIntake() {
  try { hh = await api("/api/household"); } catch { hh = {}; }
  hh = { people: hh.people || [], home: hh.home || {}, pets: hh.pets || "" };
  hhBuild(); hhAt = hh.people.some((p) => p.name) ? 1 : 0;
  hhRender();
  if (!hhDlg.open) hhDlg.showModal();
}

function closeIntake() {
  try { localStorage.setItem("hh-seen", "1"); } catch {}
  hhDlg.close();
}

$("#hhNext").onclick = async () => {
  hhCollect();
  if (hhSteps[hhAt].kind === "review") {
    try {
      const saved = await api("/api/household", {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(hh) });
      closeIntake();
      $("#hhCard")?.remove();
      log.insertAdjacentHTML("beforeend",
        `<p class="toast">Household saved: ${saved.people.length} ${saved.people.length === 1 ? "person" : "people"}. Answers now use it.</p>`);
      refresh();
    } catch (e) { hhBody.insertAdjacentHTML("beforeend", `<p class="err">Could not save: ${esc(String(e))}</p>`); }
    return;
  }
  hhAt++; hhRender();
};
$("#hhBack").onclick = () => {
  if (hhAt === 0) return closeIntake();
  hhCollect(); hhAt--; hhRender();
};
$("#hhAdd").onclick = () => {
  hhCollect(); hh.people.push({}); hhBuild();
  hhAt = hhSteps.findIndex((s) => s.kind === "person" && s.i === hh.people.length - 1); hhRender();
};
$("#hhClose").onclick = closeIntake;
hhDlg.addEventListener("cancel", (e) => { e.preventDefault(); closeIntake(); });
$("#hhBtn").onclick = openIntake;

// First visit with no household: open the intake once, and keep a card on the welcome screen.
let hhOffered = false;
function maybeOfferIntake() {
  if (hhOffered) return;
  hhOffered = true;
  const w = $("#welcome");
  if (w && !$("#hhCard")) {
    w.insertAdjacentHTML("beforeend", `<div class="hh-card" id="hhCard"><p><b>Tailor answers to your family.</b>
      Add ages, weights, allergies, and medicines so answers fit the person you're helping.</p>
      <button type="button" class="primary" id="hhCardBtn">Set up household</button></div>`);
    $("#hhCardBtn").onclick = openIntake;
  }
  let seen = null;
  try { seen = localStorage.getItem("hh-seen"); } catch {}
  if (!seen && w) openIntake();
}

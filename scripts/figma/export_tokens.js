/*
 * Figma-Variablen und -Stile als design/tokens/tokens.json exportieren.
 *
 * Dieses Skript laeuft nicht mit Node, sondern im Figma-Plugin-Kontext der Datei
 * "Maintenance AI — Design System & Redesign" (fileKey deuGeWiSr5GIZGzPENwo7p).
 * Claude Code fuehrt es ueber die Figma-MCP-Anbindung (use_figma) aus; der
 * Rueckgabewert wird unveraendert als tokens.json gespeichert. Danach:
 * npm run build:tokens.
 *
 * Abbildung:
 *   Sammlung "1 Primitives"          -> Set core            color.<rampe>.<stufe>
 *   Sammlung "2 Semantic", Light     -> Set semantic        color.<gruppe>.<rolle>
 *   Sammlung "2 Semantic", Dark      -> Set semantic-dark   dieselben Pfade
 *   Sammlung "3 Layout"              -> Set layout          space / radius / size in px
 *   Textstile (Familie je Rolle)     -> Set typography      font.display / label / body / mono
 *   Effektstile elevation/*          -> Set effects         elevation.<stufe>
 *
 * App-eigene Namen, die Figma nicht kennt (--sidebar-width, Breakpoints), stehen
 * in design/tokens/app.json und werden hier nicht beruehrt.
 */

const TYPOGRAPHY_ROLES = {
  display: "heading/xl",
  label: "overline",
  body: "body/md",
  mono: "mono/md"
};

/** Return a lowercase hex string, with alpha only when it is not opaque. */
function hex(color) {
  const channel = (value) => Math.round(value * 255).toString(16).padStart(2, "0");
  const alpha = color.a === undefined || color.a >= 1 ? "" : channel(color.a);
  return `#${channel(color.r)}${channel(color.g)}${channel(color.b)}${alpha}`;
}

/** Write a DTCG token into a nested object at a slash- or array-separated path. */
function put(target, path, token) {
  let node = target;
  for (const segment of path.slice(0, -1)) node = node[segment] ??= {};
  node[path[path.length - 1]] = token;
}

/** Return the rgba() string for a Figma color. */
function rgba(color) {
  const c = (value) => Math.round(value * 255);
  return `rgba(${c(color.r)}, ${c(color.g)}, ${c(color.b)}, ${Math.round(color.a * 1000) / 1000})`;
}

const collections = await figma.variables.getLocalVariableCollectionsAsync();
const variables = await figma.variables.getLocalVariablesAsync();
const byId = new Map(variables.map((variable) => [variable.id, variable]));
const collection = (name) => collections.find((item) => item.name === name);

const primitives = collection("1 Primitives");
const semantic = collection("2 Semantic");
const layout = collection("3 Layout");
if (!primitives || !semantic || !layout) throw new Error("Erwartete Variablensammlungen fehlen.");

const alias = (raw) => {
  const target = byId.get(raw.id);
  if (!target || target.variableCollectionId !== primitives.id) {
    throw new Error(`Semantischer Alias zeigt nicht auf ein Primitiv: ${raw.id}`);
  }
  return `{${target.name.split("/").join(".")}}`;
};

const payload = { core: {}, semantic: {}, "semantic-dark": {}, layout: {}, typography: {}, effects: {} };

for (const variable of variables.filter((item) => item.variableCollectionId === primitives.id)) {
  const value = variable.valuesByMode[primitives.defaultModeId];
  put(payload.core, variable.name.split("/"), { $type: "color", $value: hex(value) });
}

const light = semantic.modes.find((mode) => mode.name === "Light").modeId;
const dark = semantic.modes.find((mode) => mode.name === "Dark").modeId;
for (const variable of variables.filter((item) => item.variableCollectionId === semantic.id)) {
  const path = ["color", ...variable.name.split("/")];
  for (const [set, mode] of [["semantic", light], ["semantic-dark", dark]]) {
    const raw = variable.valuesByMode[mode];
    const value = raw && raw.type === "VARIABLE_ALIAS" ? alias(raw) : hex(raw);
    put(payload[set], path, { $type: "color", $value: value });
  }
}

for (const variable of variables.filter((item) => item.variableCollectionId === layout.id)) {
  const value = variable.valuesByMode[layout.defaultModeId];
  put(payload.layout, variable.name.split("/"), { $type: "dimension", $value: `${value}px` });
}

const textStyles = await figma.getLocalTextStylesAsync();
for (const [role, styleName] of Object.entries(TYPOGRAPHY_ROLES)) {
  const style = textStyles.find((item) => item.name === styleName);
  if (!style) throw new Error(`Textstil fuer Rolle ${role} fehlt: ${styleName}`);
  put(payload.typography, ["font", role], { $type: "fontFamily", $value: style.fontName.family });
}

const effectStyles = await figma.getLocalEffectStylesAsync();
for (const style of effectStyles.filter((item) => item.name.startsWith("elevation/"))) {
  const shadows = style.effects
    .filter((effect) => effect.visible !== false && (effect.type === "DROP_SHADOW" || effect.type === "INNER_SHADOW"))
    .map((effect) => {
      const inset = effect.type === "INNER_SHADOW" ? "inset " : "";
      return `${inset}${effect.offset.x}px ${effect.offset.y}px ${effect.radius}px ${effect.spread ?? 0}px ${rgba(effect.color)}`;
    });
  put(payload.effects, style.name.split("/"), { $type: "shadow", $value: shadows.join(", ") || "none" });
}

payload.$metadata = {
  source: "figma:deuGeWiSr5GIZGzPENwo7p",
  tokenSetOrder: ["core", "semantic", "semantic-dark", "layout", "typography", "effects"]
};

return payload;

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const repositoryRoot = resolve(import.meta.dirname, "../..");
const panel = () => readFileSync(resolve(repositoryRoot, "Panel.qml"), "utf8");
const tabs = () => readFileSync(resolve(repositoryRoot, "qml/components/SourceTabStrip.qml"), "utf8");
const sourceContent = () => readFileSync(resolve(repositoryRoot, "qml/components/SourceContent.qml"), "utf8");
const design = () => readFileSync(resolve(repositoryRoot, "DESIGN.md"), "utf8");
const updates = () => readFileSync(resolve(repositoryRoot, "qml/components/UpdateListView.qml"), "utf8");
const updateModel = () => readFileSync(resolve(repositoryRoot, "qml/models/UpdateViewModel.js"), "utf8");

test("uses an explicit text-only Refresh control after the glyph rejection", () => {
  const source = panel();

  assert.match(source, /text:\s*root\.panelView\.refreshText/);
  assert.match(source, /tooltipText:\s*root\.panelView\.refreshText \+ " source scan"/);
  assert.doesNotMatch(source, /\\uf0450/);
  assert.doesNotMatch(source, /iconText: root\.panelView\.refreshText === "Refreshing" \? "\.\.\." : "R"/);
});

test("keeps the tab grid as one focus stop with horizontal selection routing", () => {
  const source = tabs();

  assert.match(source, /FocusScope/);
  assert.match(source, /activeFocusOnTab:\s*true/);
  assert.match(source, /hasCursor:\s*root\.activeFocus && root\.selectedTab === modelData\.name/);
  assert.match(source, /focusable:\s*false/);
  assert.match(source, /Keys\.onLeftPressed/);
  assert.match(source, /Keys\.onRightPressed/);
  assert.doesNotMatch(source, /Qt\.Key_Up|Qt\.Key_Down/);
  assert.doesNotMatch(source, /KeyNavigation\.tab/);
  assert.doesNotMatch(sourceContent(), /activeFocusOnTab:\s*true/);
  assert.match(sourceContent(), /readonly property Item primaryControl: tab === "Security" \? securityView\.primaryControl : browseButton/);
});

test("groups the requested top-right controls with a truthful settings placeholder", () => {
  const source = panel();

  assert.match(source, /objectName:\s*"update-all"/);
  assert.match(source, /text:\s*"Update all"/);
  assert.match(source, /onClicked:\s*root\.requestUpdateAll\(\)/);
  assert.match(source, /objectName:\s*"settings-coming-later"/);
  assert.match(source, /text:\s*"Settings \(coming later\)"/);
  assert.match(source, /tooltipText:\s*"Settings coming later\."/);
  assert.match(source, /enabled:\s*false/);
});

test("uses a problem-first panel structure instead of a vague source-health label", () => {
  const source = panel();

  assert.match(source, /PanelProblemSummary/);
  assert.doesNotMatch(source, /detail:\s*root\.serviceAvailable \? "Source health" : "Unavailable"/);
  assert.doesNotMatch(source, /text:\s*"Last scan attempt:/);
  assert.doesNotMatch(updateModel(), /Source health:/);
  assert.ok(source.indexOf("PanelProblemSummary") < source.indexOf("SourceTabStrip"));
  assert.ok(source.indexOf("SourceTabStrip") < source.indexOf("SourceContent"));
});

test("uses a responsive tab grid with visible bounded health content", () => {
  const source = tabs();

  assert.match(source, /Grid/);
  assert.match(source, /columns:\s*root\.columnCount/);
  assert.match(source, /readonly property int columnCount/);
  assert.match(source, /readonly property int tabButtonCount/);
  assert.match(source, /Text \{[\s\S]*id: tabHealthItem[\s\S]*text: modelData\.healthText/);
  assert.match(source, /wrapMode: Text\.Wrap/);
  assert.match(source, /clip: true/);
  assert.doesNotMatch(source, /ListView/);
  assert.doesNotMatch(source, /HorizontalFlick/);
});

test("defines useful empty-state hierarchy and the Omarchy-native visual contract", () => {
  assert.match(updates(), /emptyTitle/);
  assert.match(updates(), /emptyDetail/);
  assert.match(design(), /## 5\. Components[\s\S]*Panel Problem Summary/);
  assert.match(design(), /focal hierarchy/i);
  assert.match(design(), /responsive/i);
});

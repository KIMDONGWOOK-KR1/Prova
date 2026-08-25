// Prova Figma 픽스처 자동 생성 (specs/2026-08-25-figma-stage1-design.md)
//
// 데스크톱 앱: Plugins > Development > Import plugin from manifest… 로 이 폴더의
// manifest.json 을 고른 뒤, Plugins > Development > Prova Fixture Generator 실행.
// 빈 파일에서 한 번만 실행한다 — 재실행하면 중복 생성된다.

async function main() {
  var font = { family: "Inter", style: "Regular" };
  try {
    await figma.loadFontAsync({ family: "Noto Sans KR", style: "Regular" });
    font = { family: "Noto Sans KR", style: "Regular" };
  } catch (e) {
    await figma.loadFontAsync(font);
  }
  await figma.loadFontAsync(font);

  function mkText(layerName, chars, x, y) {
    var t = figma.createText();
    t.fontName = font;
    t.characters = chars;
    t.name = layerName;
    t.x = x;
    t.y = y;
    return t;
  }

  function mkRect(w, h, x, y) {
    var r = figma.createRectangle();
    r.resize(w, h);
    r.x = x;
    r.y = y;
    r.cornerRadius = 6;
    r.fills = [{ type: "SOLID", color: { r: 0.93, g: 0.94, b: 0.96 } }];
    return r;
  }

  function mkComponent(name, w, h, children) {
    var c = figma.createComponent();
    c.name = name;
    c.resizeWithoutConstraints(w, h);
    for (var i = 0; i < children.length; i++) {
      c.appendChild(children[i]);
    }
    return c;
  }

  var page = figma.currentPage;

  var input = mkComponent("Input", 260, 64, [
    mkText("label", "라벨", 0, 0),
    mkRect(260, 36, 0, 24),
    mkText("placeholder", "안내 문구", 10, 32),
  ]);
  var button = mkComponent("Button", 260, 40, [
    mkRect(260, 40, 0, 0),
    mkText("text", "버튼", 100, 10),
  ]);
  var checkbox = mkComponent("Checkbox", 200, 20, [
    mkRect(16, 16, 0, 2),
    mkText("text", "체크박스", 24, 0),
  ]);
  var select = mkComponent("Select", 260, 130, [
    mkText("label", "라벨", 0, 0),
    mkRect(260, 36, 0, 24),
    mkText("option", "항목1", 10, 66),
    mkText("option", "항목2", 10, 88),
    mkText("option", "항목3", 10, 110),
  ]);

  var comps = [input, button, checkbox, select];
  var cy = 0;
  for (var ci = 0; ci < comps.length; ci++) {
    page.appendChild(comps[ci]);
    comps[ci].x = -400;
    comps[ci].y = cy;
    cy = cy + comps[ci].height + 40;
  }

  function place(comp, frame, y, texts) {
    var inst = comp.createInstance();
    frame.appendChild(inst);
    inst.x = 40;
    inst.y = y;
    var layers = Object.keys(texts);
    for (var li = 0; li < layers.length; li++) {
      var layer = layers[li];
      var contents = texts[layer];
      var list = Array.isArray(contents) ? contents : [contents];
      var nodes = inst.findAll(function (n) {
        return n.type === "TEXT" && n.name === layer;
      });
      for (var ni = 0; ni < nodes.length; ni++) {
        if (list[ni] !== undefined) {
          nodes[ni].characters = list[ni];
        }
      }
    }
    return inst;
  }

  var login = figma.createFrame();
  login.name = "로그인";
  login.resize(360, 560);
  login.x = 0;
  login.y = 0;
  page.appendChild(login);
  place(input, login, 40, { label: "이메일", placeholder: "이메일을 입력하세요" });
  place(input, login, 130, { label: "비밀번호", placeholder: "비밀번호를 입력하세요" });
  place(button, login, 230, { text: "로그인" });

  // 함정: 컴포넌트가 아닌 가짜 입력란 — "컴포넌트가 아니면 경고" 경로 검증용
  var trapRect = mkRect(260, 36, 40, 320);
  var trapText = mkText("text", "주소를 입력하세요", 50, 328);
  var trap = figma.group([trapRect, trapText], login);
  trap.name = "가짜 입력란";

  var signup = figma.createFrame();
  signup.name = "회원가입";
  signup.resize(360, 760);
  signup.x = 460;
  signup.y = 0;
  page.appendChild(signup);
  place(input, signup, 40, { label: "이메일", placeholder: "이메일을 입력하세요" });
  place(input, signup, 130, { label: "비밀번호", placeholder: "비밀번호를 입력하세요" });
  place(input, signup, 220, { label: "비밀번호 확인", placeholder: "비밀번호를 다시 입력하세요" });
  place(input, signup, 310, { label: "닉네임", placeholder: "닉네임을 입력하세요" });
  place(select, signup, 400, { label: "가입 경로", option: ["검색", "지인 추천", "광고"] });
  place(checkbox, signup, 560, { text: "약관 동의" });
  var submitBtn = place(button, signup, 610, { text: "가입하기" });

  // prototype 연결: 가입하기 -> 로그인
  var wired = true;
  try {
    var reaction = {
      trigger: { type: "ON_CLICK" },
      actions: [{
        type: "NODE",
        destinationId: login.id,
        navigation: "NAVIGATE",
        transition: null,
        resetVideoPosition: false,
      }],
    };
    if (submitBtn.setReactionsAsync) {
      await submitBtn.setReactionsAsync([reaction]);
    } else {
      submitBtn.reactions = [{ trigger: reaction.trigger, action: reaction.actions[0] }];
    }
  } catch (e) {
    wired = false;
  }

  figma.viewport.scrollAndZoomIntoView([login, signup]);
  if (wired) {
    figma.closePlugin("✅ 완료 — prototype 연결까지 됐습니다");
  } else {
    figma.closePlugin("✅ 요소 완료 — prototype 연결만 수동: 가입하기 선택 → Prototype 탭 → 로그인 프레임으로 드래그");
  }
}

main();

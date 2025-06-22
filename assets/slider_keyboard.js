/* assets/slider_keyboard.js
   모든 페이지 공통: 좌/우 방향키로 현재 표시중인 시간 슬라이더(time-slider, time-slider-section, analysis-time-slider)를 1 step씩 이동
   - 현재 보이는(visible) 슬라이더를 탐색 후 값 변경
   - dash_clientside.set_props 를 사용하여 Dash 컴포넌트 value 속성을 업데이트 → 파이썬 콜백 자동 트리거
*/

window.addEventListener('load', () => {
  if (window.sliderKeyHandlerInstalled) return;
  window.sliderKeyHandlerInstalled = true;

  document.addEventListener('keydown', (e) => {
    // 입력 필드에서 타이핑 중이면 무시
    const tag = (e.target || {}).tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || (e.target && e.target.isContentEditable)) return;

    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;

    const candidateIds = ['time-slider', 'time-slider-section', 'analysis-time-slider'];
    let activeId = null;

    // 가장 먼저 화면에 보이는(slider.offsetParent !== null) 슬라이더를 찾음
    for (const id of candidateIds) {
      const el = document.getElementById(id);
      if (el && el.offsetParent !== null) {
        activeId = id;
        break;
      }
    }

    if (!activeId) return;

    const sliderEl = document.getElementById(activeId);
    const handle = sliderEl.querySelector('.rc-slider-handle');
    if (!handle) return;

    const min = parseInt(handle.getAttribute('aria-valuemin')) || 0;
    const max = parseInt(handle.getAttribute('aria-valuemax')) || 0;
    let value = parseInt(handle.getAttribute('aria-valuenow')) || 0;

    if (e.key === 'ArrowLeft') {
      value = Math.max(min, value - 1);
    } else if (e.key === 'ArrowRight') {
      value = Math.min(max, value + 1);
    }

    // 값이 변하지 않았다면 종료
    if (value === parseInt(handle.getAttribute('aria-valuenow'))) return;

    // Dash 컴포넌트 prop 업데이트 (파이썬/다른 콜백 자동 트리거)
    if (window.dash_clientside && window.dash_clientside.set_props) {
      window.dash_clientside.set_props(activeId, { value });
    } else {
      // Fallback: 기존 방법 (핸들/트랙 수동 이동) – Dash 버전 <2.16 일때
      const percentage = ((value - min) / (max - min)) * 100;
      handle.style.left = percentage + '%';
      handle.setAttribute('aria-valuenow', value);
      const track = sliderEl.querySelector('.rc-slider-track');
      if (track) track.style.width = percentage + '%';
    }
  });

  // 추가: 슬라이더 값 변경 시 다른 슬라이더들도 동일 값으로 동기화
  function syncOtherSliders(sourceId, newValue) {
    const ids = ['time-slider', 'time-slider-section', 'analysis-time-slider'];
    ids.forEach(id => {
      if (id === sourceId) return;
      const el = document.getElementById(id);
      if (!el) return;
      if (window.dash_clientside && window.dash_clientside.set_props) {
        window.dash_clientside.set_props(id, { value: newValue });
      }
    });
  }

  // candidate slider 변경 감지하여 동기화
  ['time-slider', 'time-slider-section', 'analysis-time-slider'].forEach(sid => {
    document.addEventListener('change', (ev) => {
      const t = ev.target;
      if (!t) return;
      // rc-slider는 handle 내부 span이 change 이벤트를 발생시키지 않을 수 있어 부모 슬라이더 체크
      let sliderEl = t.closest?.('.rc-slider');
      if (!sliderEl) return;
      if (sliderEl.id !== sid) return;
      const handle = sliderEl.querySelector('.rc-slider-handle');
      if (!handle) return;
      const newVal = parseInt(handle.getAttribute('aria-valuenow'));
      if (isNaN(newVal)) return;
      syncOtherSliders(sliderEl.id, newVal);
    });
  });
}); 
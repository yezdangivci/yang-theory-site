import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import edit from './public/film/yang-theory-film.json';

gsap.registerPlugin(ScrollTrigger);

const stage = document.querySelector('#filmStage');
const video = document.querySelector('#filmVideo');
const loading = document.querySelector('#filmLoading');
const retry = document.querySelector('#filmRetry');
const header = document.querySelector('#siteHeader');
const copy = document.querySelector('#filmCopy');
const meta = document.querySelector('.film-meta');
const title = document.querySelector('#filmTitle');
const type = document.querySelector('#filmType');
const subtitle = document.querySelector('#filmSubtitle');
const counter = document.querySelector('#filmCounter');
const cta = document.querySelector('#filmCta');
const progress = document.querySelector('#filmProgress');
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const clamp = (x, a=0, b=1) => Math.min(b, Math.max(a, x));
const texts = [
  ['01 — Wearable art', 'Zaru', 'A handmade artifact. A world within the stone.'],
  ['02 — Original story world', 'Journey', 'The forest answers when curiosity reaches out.'],
  ['03 — Material experiments', 'Seek Magic', 'Color, crystal and a universe on a tabletop.'],
  ['04 — Wearable art', 'Ophelia', 'Sculpted by hand. Defined by a red stone.'],
  ['05 — Hand-painted objects', 'Shila', 'The timeless queen. An everyday object reimagined.'],
  ['06 — Journey films', 'Burton', 'The guide takes flight.'],
];
const chapters = edit.chapters;
let trigger, desired = 0, requestedProgress = 0, presented = 0;
let ready = false, busy = false, request = 0;

function chapterAt(time) {
  return chapters.findLast(chapter => time + .001 >= chapter.start)?.index || 0;
}

function updateCopy(time) {
  const i = chapterAt(time);
  const maker = i === 5 && time >= chapters[5].start + 3.8;
  const text = maker ? ['06 — Creative production', 'Behind the world', 'Every story begins with a maker.'] : texts[i];
  [type.textContent, title.textContent, subtitle.textContent] = text;
  counter.textContent = `${String(i+1).padStart(2, '0')} / 06`;
  copy.classList.toggle('is-maker', maker);
  const light = i === 2 || i === 3 || i === 4;
  copy.classList.toggle('is-light', light);
  meta.classList.toggle('is-light', light);
  cta.hidden = !(maker && time >= chapters[5].start + 5.1);
  progress.style.transform = `scaleX(${requestedProgress})`;
  stage.dataset.scene = String(i);
  stage.dataset.progress = String(requestedProgress);
  stage.dataset.frameTime = String(time);
  // This only joins the film's letterbox margins to its existing ground.
  // Subject placement and all transitions belong to the rendered master.
  stage.dataset.ground = i === 2 ? 'table' : i === 3 || i === 4 ? 'ivory' : 'dark';
}

function updateHeader() {
  header.classList.toggle('in-film', Boolean(trigger?.isActive));
  header.classList.toggle('film-light', Boolean(trigger?.isActive && [2,3,4].includes(chapterAt(presented))));
  const journey = document.querySelector('#journey');
  header.classList.toggle('on-light', Boolean(trigger && !trigger.isActive && scrollY > trigger.end && scrollY < journey.offsetTop));
}

function finishSeek() {
  if (video.readyState < 2) return;
  // A decoded paused frame gets two presentation turns on both Chromium and
  // WebKit. There is one seek in flight; newer scroll targets replace the queue.
  requestAnimationFrame(() => requestAnimationFrame(() => {
    presented = video.currentTime;
    busy = false;
    updateCopy(presented);
    updateHeader();
    pump();
  }));
}

function pump() {
  if (!ready || busy || video.seeking) return;
  if (Math.abs(video.currentTime - desired) < .45 / edit.fps) {
    updateCopy(presented);
    return;
  }
  busy = true;
  video.currentTime = desired;
}

function queue(progressValue) {
  requestedProgress = clamp(progressValue);
  let time = requestedProgress * (edit.duration - 1/edit.fps);
  if (reducedMotion) {
    const i = chapterAt(time);
    // Preserve native scrolling while showing stable source moments for people
    // who request reduced motion. Normal mode maps every frame continuously.
    time = i === 0 ? 7 : i === 5 ? chapters[5].start + 6 : chapters[i].start + Math.min(2, chapters[i].end-chapters[i].start-.1);
  }
  desired = Math.round(clamp(time, 0, video.duration-1/edit.fps) * edit.fps) / edit.fps;
  stage.dataset.desiredTime = String(desired);
  if (!request) request = requestAnimationFrame(() => { request = 0; pump(); });
}

function start() {
  if (ready) return;
  ready = true;
  stage.classList.add('is-ready');
  loading.hidden = true;
  retry.hidden = true;
  presented = video.currentTime;
  trigger = ScrollTrigger.create({
    id: 'yang-film', trigger: '#film', pin: stage, start: 'top top',
    end: () => `+=${Math.max(5400, stage.clientHeight * 7.8)}`,
    scrub: true, anticipatePin: 1, invalidateOnRefresh: true,
    onUpdate: self => { queue(self.progress); updateHeader(); },
    onRefresh: self => { queue(self.progress); updateHeader(); },
    onToggle: updateHeader,
  });
  updateCopy(presented);
  ScrollTrigger.refresh();
  queue(trigger.progress);
  document.fonts.ready.then(() => ScrollTrigger.refresh());
}

video.addEventListener('loadeddata', start);
video.addEventListener('seeked', finishSeek);
video.addEventListener('loadedmetadata', () => {
  if (video.readyState >= 2) start();
  else video.currentTime = 1/edit.fps;
});
video.addEventListener('error', () => {
  loading.hidden = false;
  loading.querySelector('small').textContent = 'The film could not load. Please retry.';
  retry.hidden = false;
});
// iOS may defer media preparation until the first native interaction. No input
// is intercepted or cancelled, and the only video remains paused for scrolling.
document.addEventListener('touchstart', () => {
  if (!ready) video.load();
}, { once: true, passive: true });
window.addEventListener('scroll', updateHeader, { passive: true });
window.addEventListener('pageshow', () => { ScrollTrigger.refresh(); if (trigger) queue(trigger.progress); });
document.addEventListener('visibilitychange', () => { if (!document.hidden && trigger) queue(trigger.progress); });
retry.addEventListener('click', () => location.reload());
if (video.readyState >= 2) start();
else video.load();

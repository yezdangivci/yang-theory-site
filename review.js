const film = document.querySelector('#film');
const play = document.querySelector('#playFilm');
const pause = document.querySelector('#pauseFilm');
const replay = document.querySelector('#replayFilm');
const status = document.querySelector('#playbackStatus');
const number = document.querySelector('#beatNumber');
const title = document.querySelector('#beatTitle');
const line = document.querySelector('#beatLine');
const beats = [
  [0, '01 / 06 — Wearable art', 'Zaru', 'A world within the stone.'],
  [6.5, '02 / 06 — Story world', 'Journey', 'Curiosity opens another world.'],
  [10.15, '03 / 06 — Art & objects', 'Seek Magic', 'A universe on a tabletop.'],
  [14.8, '04 / 06 — Wearable art', 'Ophelia', 'Sculpted by hand. Defined by a red stone.'],
  [20.35, '05 / 06 — Hand-painted objects', 'Shila', 'The timeless queen.'],
  [24.45, '06 / 06 — Journey films', 'Burton', 'The guide takes flight.'],
  [28.3, '06 / 06 — The studio', 'Behind the world', 'Every world begins with a maker.'],
];

function updateCopy() {
  const beat = beats.findLast(item => film.currentTime >= item[0]) || beats[0];
  number.textContent = beat[1];
  title.textContent = beat[2];
  line.textContent = beat[3];
}

async function start() {
  status.textContent = 'Loading the film…';
  try { await film.play(); status.textContent = ''; }
  catch { status.textContent = 'Playback could not start. Please try Play again or use the video controls.'; }
}
play.addEventListener('click', () => { if (film.ended) film.currentTime = 0; start(); });
pause.addEventListener('click', () => film.paused ? start() : film.pause());
replay.addEventListener('click', () => { film.currentTime = 0; start(); });
film.addEventListener('play', () => { play.hidden = true; pause.disabled = false; pause.textContent = 'Pause'; });
film.addEventListener('playing', () => { status.textContent = ''; });
film.addEventListener('pause', () => { pause.textContent = 'Resume'; });
film.addEventListener('ended', () => { play.hidden = false; play.innerHTML = '<span aria-hidden="true">↺</span> REPLAY FILM'; pause.disabled = true; });
film.addEventListener('error', () => { status.textContent = 'The film could not be loaded. Please reload this page.'; play.hidden = false; });
film.addEventListener('timeupdate', updateCopy);
film.addEventListener('seeked', () => {
  updateCopy();
  if (!film.ended) { pause.disabled = false; play.hidden = true; }
});
updateCopy();

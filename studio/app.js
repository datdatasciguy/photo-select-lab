const $ = (id) => document.getElementById(id);

const source = $('source-video');
const result = $('result-video');
const clips = { source: null, result: null };
let start = 0;
let end = 0;

function timeLabel(seconds) {
  if (!Number.isFinite(seconds)) return '0:00.00';
  const minutes = Math.floor(seconds / 60);
  const rest = (seconds % 60).toFixed(2).padStart(5, '0');
  return `${minutes}:${rest}`;
}

function sizeLabel(bytes) {
  if (bytes == null) return 'Bundled demo';
  return bytes < 1048576 ? `${(bytes / 1024).toFixed(0)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;
}

function setStatus(message) {
  $('status').textContent = message;
}

function pauseClips() {
  source.pause();
  result.pause();
  $('play-toggle').textContent = '▶';
  $('play-toggle').setAttribute('aria-label', 'Play selected clip');
}

function seekTo(seconds) {
  if (!clips.source) return;
  const position = Math.max(start, Math.min(end, seconds));
  source.currentTime = position;
  if (clips.result && Number.isFinite(result.duration)) {
    result.currentTime = Math.min(position, result.duration);
  }
  $('scrubber').value = String(position);
  $('current-time').textContent = timeLabel(position);
}

function showRange() {
  $('range-start').value = start.toFixed(2);
  $('range-end').value = end.toFixed(2);
  $('scrubber').min = String(start);
  $('scrubber').max = String(end);
  $('range-readout').textContent = `${timeLabel(start)} → ${timeLabel(end)} · ${(end - start).toFixed(2)}s selected`;
}

function updateRange(changed) {
  if (!Number.isFinite(source.duration)) return;
  const duration = source.duration;
  const requestedStart = Number($('range-start').value);
  const requestedEnd = Number($('range-end').value);
  if (!Number.isFinite(requestedStart) || !Number.isFinite(requestedEnd)) {
    showRange();
    return;
  }
  start = Math.max(0, Math.min(duration, requestedStart));
  end = Math.max(0, Math.min(duration, requestedEnd));
  if (start >= end) {
    if (changed === 'start') start = Math.max(0, end - 0.01);
    else end = Math.min(duration, start + 0.01);
  }
  if (start >= end) {
    start = 0;
    end = duration;
  }
  pauseClips();
  showRange();
  seekTo(start);
}

function loadClip(kind, url, name, bytes, owned) {
  pauseClips();
  if (clips[kind]?.owned) URL.revokeObjectURL(clips[kind].url);
  clips[kind] = { url, owned };
  if (kind === 'source') {
    for (const id of ['play-toggle', 'step-back', 'step-forward', 'scrubber', 'range-start', 'range-end', 'use-full']) {
      $(id).disabled = true;
    }
    $('detail-size').textContent = sizeLabel(bytes);
  }
  const video = kind === 'source' ? source : result;
  video.src = url;
  video.load();
  $(`${kind}-file`).textContent = `${name} · ${sizeLabel(bytes)}`;
  $(`${kind}-empty`).hidden = true;
  $(`${kind}-resolution`).textContent = 'Loading…';
  setStatus(`${kind === 'source' ? 'Original' : 'Result'} loaded for local review: ${name}`);
}

function loadFile(kind, file) {
  if (!file) return;
  if (!file.type.startsWith('video/') && !/\.(mp4|mov|m4v|webm|ogv)$/i.test(file.name)) {
    setStatus('Choose a video file. This browser will report if its codec is unsupported.');
    return;
  }
  loadClip(kind, URL.createObjectURL(file), file.name, file.size, true);
}

function onMetadata(kind) {
  const video = kind === 'source' ? source : result;
  $(`${kind}-resolution`).textContent = `${video.videoWidth} × ${video.videoHeight}`;
  if (!Number.isFinite(video.duration) || video.duration <= 0) {
    setStatus('This clip has no usable duration. Try a different video format.');
    return;
  }
  if (kind === 'source') {
    start = 0;
    end = video.duration;
    for (const id of ['play-toggle', 'step-back', 'step-forward', 'scrubber', 'range-start', 'range-end', 'use-full']) {
      $(id).disabled = false;
    }
    $('session-state').textContent = 'Ready to review';
    $('total-time').textContent = timeLabel(end);
    $('detail-duration').textContent = timeLabel(end);
    $('detail-resolution').textContent = `${video.videoWidth} × ${video.videoHeight}`;
    showRange();
    seekTo(0);
  } else {
    $('detail-result').textContent = timeLabel(video.duration);
    seekTo(source.currentTime);
    if (clips.source && video.duration + 0.05 < end) {
      setStatus('Result is shorter than the selected range. It will hold on its last frame.');
    }
  }
}

async function togglePlayback() {
  if (!clips.source) return;
  if (!source.paused) {
    pauseClips();
    return;
  }
  if (source.currentTime >= end - 0.02) seekTo(start);
  if (clips.result) seekTo(source.currentTime);
  try {
    await source.play();
    if (clips.result && Number.isFinite(result.duration) && result.currentTime < result.duration - 0.02) {
      await result.play();
    }
    $('play-toggle').textContent = 'Ⅱ';
    $('play-toggle').setAttribute('aria-label', 'Pause selected clip');
  } catch {
    pauseClips();
    setStatus('Playback failed. This browser may not support the video codec.');
  }
}

function nudgeTime(direction) {
  if (!clips.source) return;
  pauseClips();
  seekTo(source.currentTime + direction / 24);
}

function addDropTarget(kind) {
  const target = $(`${kind}-drop`);
  target.addEventListener('dragover', (event) => {
    event.preventDefault();
    target.classList.add('dragging');
  });
  target.addEventListener('dragleave', () => target.classList.remove('dragging'));
  target.addEventListener('drop', (event) => {
    event.preventDefault();
    target.classList.remove('dragging');
    loadFile(kind, event.dataTransfer.files[0]);
  });
}

for (const kind of ['source', 'result']) {
  $(`choose-${kind}`).addEventListener('click', () => $(`${kind}-input`).click());
  $(`${kind}-input`).addEventListener('change', (event) => loadFile(kind, event.target.files[0]));
  (kind === 'source' ? source : result).addEventListener('loadedmetadata', () => onMetadata(kind));
  (kind === 'source' ? source : result).addEventListener('error', () => {
    setStatus(`Could not open the ${kind} video. Check that its format plays in this browser.`);
  });
  addDropTarget(kind);
}

$('load-demo').addEventListener('click', async () => {
  $('load-demo').disabled = true;
  setStatus('Loading the bundled demo clips…');
  try {
    const responses = await Promise.all(['demo/source.mp4', 'demo/variation.mp4'].map((path) => fetch(path)));
    if (responses.some((response) => !response.ok)) throw new Error('Demo clips were not found.');
    const blobs = await Promise.all(responses.map((response) => response.blob()));
    loadClip('source', URL.createObjectURL(blobs[0]), 'Moving shapes', null, true);
    loadClip('result', URL.createObjectURL(blobs[1]), 'Grayscale variation', null, true);
    setStatus('Procedural demo loaded. It shows a comparison workflow, not a model result.');
  } catch {
    setStatus('Could not load the demo clips. Check that both files are in studio/demo.');
  } finally {
    $('load-demo').disabled = false;
  }
});

$('play-toggle').addEventListener('click', togglePlayback);
$('step-back').addEventListener('click', () => nudgeTime(-1));
$('step-forward').addEventListener('click', () => nudgeTime(1));
$('scrubber').addEventListener('input', (event) => {
  pauseClips();
  seekTo(Number(event.target.value));
});
$('range-start').addEventListener('change', () => updateRange('start'));
$('range-end').addEventListener('change', () => updateRange('end'));
$('use-full').addEventListener('click', () => {
  start = 0;
  end = source.duration;
  pauseClips();
  showRange();
  seekTo(0);
});

source.addEventListener('timeupdate', () => {
  if (!clips.source) return;
  if (source.currentTime >= end && !source.paused) {
    pauseClips();
    seekTo(end);
    return;
  }
  $('scrubber').value = String(Math.max(start, Math.min(end, source.currentTime)));
  $('current-time').textContent = timeLabel(source.currentTime);
  if (clips.result && Number.isFinite(result.duration)) {
    const position = Math.min(source.currentTime, result.duration);
    if (Math.abs(result.currentTime - position) > 0.12) result.currentTime = position;
  }
});

source.addEventListener('ended', pauseClips);
document.addEventListener('keydown', (event) => {
  if (['INPUT', 'TEXTAREA', 'BUTTON'].includes(document.activeElement.tagName)) return;
  if (event.code === 'Space') {
    event.preventDefault();
    togglePlayback();
  } else if (event.code === 'ArrowLeft' || event.code === 'ArrowRight') {
    event.preventDefault();
    nudgeTime(event.code === 'ArrowLeft' ? -1 : 1);
  }
});

window.addEventListener('beforeunload', () => {
  for (const clip of Object.values(clips)) {
    if (clip?.owned) URL.revokeObjectURL(clip.url);
  }
});

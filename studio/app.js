const $ = (id) => document.getElementById(id);

const source = $('source-video');
const result = $('result-video');
const clips = { source: null, result: null };
const compareCanvas = $('compare-canvas');
let compareFrame = null;
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

function drawContained(video, context, width, height) {
  const scale = Math.min(width / video.videoWidth, height / video.videoHeight);
  const videoWidth = video.videoWidth * scale;
  const videoHeight = video.videoHeight * scale;
  context.drawImage(video, (width - videoWidth) / 2,
                    (height - videoHeight) / 2, videoWidth, videoHeight);
}

function drawComparison() {
  if ($('compare-panel').hidden || source.readyState < 2 || result.readyState < 2) return;
  const width = Math.min(source.videoWidth, 960);
  const height = Math.round(width * source.videoHeight / source.videoWidth);
  if (compareCanvas.width !== width || compareCanvas.height !== height) {
    compareCanvas.width = width;
    compareCanvas.height = height;
  }
  const context = compareCanvas.getContext('2d');
  const split = width * Number($('compare-wipe').value) / 100;
  context.fillStyle = '#05080c';
  context.fillRect(0, 0, width, height);
  drawContained(source, context, width, height);
  context.save();
  context.beginPath();
  context.rect(0, 0, split, height);
  context.clip();
  drawContained(result, context, width, height);
  context.restore();
  context.fillStyle = '#8bdcc9';
  context.fillRect(split - 1, 0, 2, height);
  $('compare-times').textContent = timeLabel(source.currentTime) +
    ' original · ' + timeLabel(result.currentTime) + ' result';
}

function scheduleComparison() {
  if (compareFrame !== null) return;
  compareFrame = requestAnimationFrame(() => {
    compareFrame = null;
    drawComparison();
    if (!source.paused) scheduleComparison();
  });
}

function updateComparison() {
  const ready = clips.source && clips.result && source.videoWidth && result.videoWidth &&
    Number.isFinite(source.duration) && Number.isFinite(result.duration);
  $('compare-panel').hidden = !ready;
  if (!ready) return;
  const sameSize = source.videoWidth === result.videoWidth &&
    source.videoHeight === result.videoHeight;
  $('compare-note').textContent = sameSize
    ? 'Result is left of the line. Frames follow the original time.'
    : 'Clip sizes differ. Both are fitted into the original frame; edges may not line up.';
  scheduleComparison();
}

function pauseClips() {
  source.pause();
  result.pause();
  $('play-toggle').textContent = '▶';
  $('play-toggle').setAttribute('aria-label', 'Play selected clip');
}

function seekTo(seconds) {
  if (!clips.source) return;
  clearDifference();
  const position = Math.max(start, Math.min(end, seconds));
  source.currentTime = position;
  if (clips.result && Number.isFinite(result.duration)) {
    result.currentTime = Math.min(position, result.duration);
  }
  $('scrubber').value = String(position);
  $('current-time').textContent = timeLabel(position);
  scheduleComparison();
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
  const previousStart = start;
  const previousEnd = end;
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
  if (maskTime !== null && (maskTime < start || maskTime > end)) {
    start = previousStart;
    end = previousEnd;
    showRange();
    setStatus('The range must include the marked frame. Clear the mask first to change it.');
    return;
  }
  pauseClips();
  clearScan();
  showRange();
  seekTo(start);
}

const maskCanvas = $('mask-canvas');
const maskPoints = [];
let maskTime = null;
let maskMode = 'include';
let selectedPoint = -1;
let activePointer = null;
let scanRevision = 0;
let scanBusy = false;

function sourceRect() {
  if (!source.videoWidth || !source.videoHeight) return null;
  const width = maskCanvas.clientWidth;
  const height = maskCanvas.clientHeight;
  const scale = Math.min(width / source.videoWidth, height / source.videoHeight);
  const videoWidth = source.videoWidth * scale;
  const videoHeight = source.videoHeight * scale;
  return { x: (width - videoWidth) / 2, y: (height - videoHeight) / 2,
           width: videoWidth, height: videoHeight };
}

function buildMask() {
  const canvas = document.createElement('canvas');
  canvas.width = source.videoWidth;
  canvas.height = source.videoHeight;
  const context = canvas.getContext('2d');
  const shortSide = Math.min(canvas.width, canvas.height);
  for (const kind of ['include', 'exclude']) {
    context.globalCompositeOperation = kind === 'include' ? 'source-over' : 'destination-out';
    context.fillStyle = '#ffffff';
    for (const point of maskPoints.filter((item) => item.kind === kind)) {
      context.beginPath();
      context.arc(point.x * canvas.width, point.y * canvas.height,
                  point.radius * shortSide, 0, Math.PI * 2);
      context.fill();
    }
  }
  context.globalCompositeOperation = 'source-over';
  return canvas;
}

function updateMaskReadout() {
  const include = maskPoints.filter((point) => point.kind === 'include').length;
  const exclude = maskPoints.length - include;
  $('mask-frame').disabled = maskPoints.length === 0;
  $('mask-clear').disabled = maskPoints.length === 0;
  $('mask-download').disabled = include === 0;
  $('mask-delete').disabled = selectedPoint < 0;
  $('mask-readout').textContent = maskPoints.length
    ? include + ' include, ' + exclude + ' exclude at ' + timeLabel(maskTime) +
      (selectedPoint >= 0 ? '. Circle ' + (selectedPoint + 1) + ' selected.' : '.')
    : clips.source ? 'Pause and click the original preview to mark one frame.'
      : 'Load an original clip to start.';
  updateDifferenceAvailability();
}

function clearDifference() {
  $('difference-readout').textContent = 'Check the marked frame to count changed pixels.';
}

function clearScan() {
  scanRevision++;
  $('flicker-readout').textContent = 'Scan nearby frames to compare outside-mask changes.';
  $('flicker-samples').replaceChildren();
}

function updateDifferenceAvailability() {
  const hasMask = maskPoints.some((point) => point.kind === 'include');
  const ready = hasMask && clips.source && clips.result &&
    source.readyState >= 2 && result.readyState >= 2;
  $('mask-difference').disabled = !ready;
  $('flicker-scan').disabled = !ready || scanBusy;
}

function differenceSetup() {
  const scale = Math.min(1, 960 / Math.max(source.videoWidth, source.videoHeight));
  const width = Math.max(1, Math.round(source.videoWidth * scale));
  const height = Math.max(1, Math.round(source.videoHeight * scale));
  const mask = document.createElement('canvas');
  mask.width = width;
  mask.height = height;
  const maskContext = mask.getContext('2d', { willReadFrequently: true });
  maskContext.drawImage(buildMask(), 0, 0, width, height);
  return { width, height, maskPixels: maskContext.getImageData(0, 0, width, height).data };
}

function measureDifference(original, edited, setup, threshold, trackOutside = false) {
  const { width, height, maskPixels } = setup;
  const pixels = [];
  const outsideFlags = trackOutside ? new Uint8Array(width * height) : null;
  for (const video of [original, edited]) {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    context.drawImage(video, 0, 0, width, height);
    pixels.push(context.getImageData(0, 0, width, height).data);
  }
  const counts = { inside: { total: 0, changed: 0 }, outside: { total: 0, changed: 0 } };
  for (let index = 0; index < pixels[0].length; index += 4) {
    const group = maskPixels[index + 3] > 0 ? counts.inside : counts.outside;
    group.total++;
    const changed = Math.max(Math.abs(pixels[0][index] - pixels[1][index]),
                 Math.abs(pixels[0][index + 1] - pixels[1][index + 1]),
                 Math.abs(pixels[0][index + 2] - pixels[1][index + 2])) >= threshold;
    if (changed) group.changed++;
    if (outsideFlags && group === counts.outside) outsideFlags[index / 4] = Number(changed);
  }
  counts.outsideFlags = outsideFlags;
  return counts;
}

function checkDifference() {
  if (!maskPoints.some((point) => point.kind === 'include') || !clips.result) return;
  if (source.videoWidth !== result.videoWidth || source.videoHeight !== result.videoHeight) {
    $('difference-readout').textContent = 'Clip resolutions differ. Use matching dimensions for a pixel check.';
    return;
  }
  if (!source.paused || !result.paused || source.seeking || result.seeking ||
      source.readyState < 2 || result.readyState < 2 ||
      Math.abs(source.currentTime - maskTime) > 0.05 ||
      Math.abs(result.currentTime - maskTime) > 0.05) {
    $('difference-readout').textContent = 'Pause both clips at the marked frame, then try again.';
    return;
  }
  try {
    const setup = differenceSetup();
    const threshold = Number($('difference-threshold').value);
    const counts = measureDifference(source, result, setup, threshold);
    const label = (group) => group.total
      ? `${group.changed.toLocaleString()} / ${group.total.toLocaleString()} (${(100 * group.changed / group.total).toFixed(1)}%)`
      : 'no pixels';
    $('difference-readout').textContent =
      `Outside mask: ${label(counts.outside)} changed. Inside mask: ${label(counts.inside)} changed. ` +
      `${setup.width} × ${setup.height} sampled pixels; any RGB channel differs by at least ${threshold}.`;
  } catch {
    $('difference-readout').textContent = 'Could not read these video frames for a pixel check.';
  }
}

function waitForVideo(video, eventName) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => finish(false), 12000);
    const ready = () => finish(true);
    const failed = () => finish(false);
    function finish(ok) {
      clearTimeout(timeout);
      video.removeEventListener(eventName, ready);
      video.removeEventListener('error', failed);
      if (ok) resolve();
      else reject(new Error('Video frame was unavailable.'));
    }
    video.addEventListener(eventName, ready);
    video.addEventListener('error', failed);
  });
}

async function scanVideo(url) {
  const video = document.createElement('video');
  video.preload = 'auto';
  video.muted = true;
  const ready = waitForVideo(video, 'loadeddata');
  video.src = url;
  video.load();
  await ready;
  return video;
}

async function seekScanVideo(video, seconds) {
  if (Math.abs(video.currentTime - seconds) < 0.005 && video.readyState >= 2) return;
  const ready = waitForVideo(video, 'seeked');
  video.currentTime = seconds;
  await ready;
  if (video.readyState < 2) await waitForVideo(video, 'loadeddata');
}

async function scanNearbyFrames() {
  if (scanBusy || !maskPoints.some((point) => point.kind === 'include') || !clips.result) return;
  clearScan();
  if (source.videoWidth !== result.videoWidth || source.videoHeight !== result.videoHeight) {
    $('flicker-readout').textContent = 'Clip resolutions differ. Use matching dimensions for this scan.';
    return;
  }
  if (result.duration <= maskTime) {
    $('flicker-readout').textContent = 'The result clip ends before the marked frame.';
    return;
  }
  const times = [-0.25, -0.125, 0, 0.125, 0.25]
    .map((offset) => maskTime + offset)
    .filter((time) => time >= start && time <= end && time >= 0 &&
      time < source.duration - 0.02 && time < result.duration - 0.02);
  if (times.length < 2) {
    $('flicker-readout').textContent = 'The marked frame is too close to the clip or range edge for a nearby scan.';
    return;
  }
  const revision = scanRevision;
  const setup = differenceSetup();
  const threshold = Number($('difference-threshold').value);
  let original;
  let edited;
  scanBusy = true;
  updateDifferenceAvailability();
  $('flicker-readout').textContent = `Scanning ${times.length} local frames…`;
  try {
    [original, edited] = await Promise.all([scanVideo(clips.source.url), scanVideo(clips.result.url)]);
    const samples = [];
    let previousFlags = null;
    for (const time of times) {
      if (revision !== scanRevision) return;
      await Promise.all([seekScanVideo(original, time), seekScanVideo(edited, time)]);
      const counts = measureDifference(original, edited, setup, threshold, true);
      const outside = counts.outside;
      if (!outside.total) {
        $('flicker-readout').textContent = 'The mask covers the frame, leaving no outside pixels to scan.';
        return;
      }
      let turnover = null;
      if (previousFlags) {
        let flipped = 0;
        for (let index = 0; index < counts.outsideFlags.length; index++) {
          if (counts.outsideFlags[index] !== previousFlags[index]) flipped++;
        }
        turnover = 100 * flipped / outside.total;
      }
      samples.push({ time, percent: 100 * outside.changed / outside.total, turnover });
      previousFlags = counts.outsideFlags;
    }
    if (revision !== scanRevision) return;
    const rates = samples.map((sample) => sample.percent);
    const spread = Math.max(...rates) - Math.min(...rates);
    const maxTurnover = Math.max(...samples.slice(1).map((sample) => sample.turnover));
    $('flicker-readout').textContent =
      `${samples.length} frames near ${timeLabel(maskTime)}: outside-mask changed pixels ranged ` +
      `${Math.min(...rates).toFixed(1)}–${Math.max(...rates).toFixed(1)}% ` +
      `(${spread.toFixed(1)} percentage points). Up to ${maxTurnover.toFixed(1)}% of outside pixels ` +
      `switched changed/unchanged between adjacent samples. Fixed mask, ${setup.width} × ${setup.height} sample, ` +
      `RGB threshold ${threshold}. Motion can also change these rates; inspect the frames before calling it flicker.`;
    for (const sample of samples) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = `${timeLabel(sample.time)} · ${sample.percent.toFixed(1)}%`;
      button.title = 'Jump to this sampled frame in the wipe view';
      button.addEventListener('click', () => {
        pauseClips();
        seekTo(sample.time);
      });
      $('flicker-samples').append(button);
    }
  } catch {
    if (revision === scanRevision) $('flicker-readout').textContent = 'Could not decode the nearby frames in this browser.';
  } finally {
    for (const video of [original, edited]) {
      if (video) {
        video.removeAttribute('src');
        video.load();
      }
    }
    scanBusy = false;
    updateDifferenceAvailability();
  }
}

function redrawMask() {
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(maskCanvas.clientWidth * ratio));
  const height = Math.max(1, Math.round(maskCanvas.clientHeight * ratio));
  if (maskCanvas.width !== width || maskCanvas.height !== height) {
    maskCanvas.width = width;
    maskCanvas.height = height;
  }
  const context = maskCanvas.getContext('2d');
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, maskCanvas.clientWidth, maskCanvas.clientHeight);
  const rect = sourceRect();
  if (!rect || !maskPoints.length || !source.paused ||
      Math.abs(source.currentTime - maskTime) > 0.05) return;
  context.globalAlpha = 0.35;
  context.drawImage(buildMask(), rect.x, rect.y, rect.width, rect.height);
  context.globalAlpha = 1;
  for (const [index, point] of maskPoints.entries()) {
    const x = rect.x + point.x * rect.width;
    const y = rect.y + point.y * rect.height;
    context.beginPath();
    context.arc(x, y, index === selectedPoint ? 8 : 5, 0, Math.PI * 2);
    context.fillStyle = point.kind === 'include' ? '#8bdcc9' : '#ffad9d';
    context.fill();
    context.lineWidth = index === selectedPoint ? 3 : 2;
    context.strokeStyle = index === selectedPoint ? '#ffffff' : '#10202a';
    context.stroke();
  }
}

function resetMask() {
  maskPoints.length = 0;
  maskTime = null;
  selectedPoint = -1;
  activePointer = null;
  clearDifference();
  clearScan();
  updateMaskReadout();
  redrawMask();
}

function maskPosition(event, rect) {
  const bounds = maskCanvas.getBoundingClientRect();
  return { x: event.clientX - bounds.left - rect.x, y: event.clientY - bounds.top - rect.y };
}

function markFrame(event) {
  const rect = sourceRect();
  if (!rect || !Number.isFinite(source.duration)) return;
  const { x, y } = maskPosition(event, rect);
  if (x < 0 || y < 0 || x > rect.width || y > rect.height) {
    setStatus('Click inside the video frame, not the black bars.');
    return;
  }
  pauseClips();
  if (maskTime !== null && Math.abs(source.currentTime - maskTime) > 0.05) {
    setStatus('This draft belongs to ' + timeLabel(maskTime) + '. Go to that frame or clear it first.');
    return;
  }
  if (maskMode === 'edit') {
    selectedPoint = -1;
    for (let index = maskPoints.length - 1; index >= 0; index--) {
      const point = maskPoints[index];
      if (Math.hypot(x - point.x * rect.width, y - point.y * rect.height) <= 14) {
        selectedPoint = index;
        activePointer = event.pointerId;
        maskCanvas.setPointerCapture(event.pointerId);
        break;
      }
    }
    updateMaskReadout();
    redrawMask();
    return;
  }
  if (maskTime === null) maskTime = source.currentTime;
  selectedPoint = -1;
  maskPoints.push({ x: x / rect.width, y: y / rect.height,
                    radius: Number($('mask-radius').value) / 100, kind: maskMode });
  clearDifference();
  clearScan();
  updateMaskReadout();
  redrawMask();
}

function moveMaskPoint(event) {
  if (event.pointerId !== activePointer || selectedPoint < 0) return;
  const rect = sourceRect();
  if (!rect) return;
  const { x, y } = maskPosition(event, rect);
  maskPoints[selectedPoint].x = Math.max(0, Math.min(1, x / rect.width));
  maskPoints[selectedPoint].y = Math.max(0, Math.min(1, y / rect.height));
  clearDifference();
  clearScan();
  redrawMask();
}

function finishMaskMove(event) {
  if (event.pointerId !== activePointer) return;
  activePointer = null;
  if (maskCanvas.hasPointerCapture(event.pointerId)) maskCanvas.releasePointerCapture(event.pointerId);
}

function deleteMaskPoint() {
  if (selectedPoint < 0) return;
  maskPoints.splice(selectedPoint, 1);
  clearDifference();
  clearScan();
  selectedPoint = -1;
  if (!maskPoints.length) {
    resetMask();
    return;
  }
  updateMaskReadout();
  redrawMask();
}

function downloadDraft() {
  if (!source.videoWidth || !Number.isFinite(source.duration)) return;
  const draft = {
    version: 1,
    source: { width: source.videoWidth, height: source.videoHeight, duration: source.duration },
    range: { start, end },
    mask: { time: maskTime, points: maskPoints }
  };
  const url = URL.createObjectURL(new Blob([JSON.stringify(draft, null, 2) + '\n'], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'photo-select-draft.json';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  setStatus('Saved range and mask settings. The JSON contains no video or image pixels.');
}

function validDraft(draft) {
  const finite = (value) => typeof value === 'number' && Number.isFinite(value);
  if (!draft || draft.version !== 1 || !draft.source || !draft.range || !draft.mask) return false;
  const { width, height, duration } = draft.source;
  const { start: rangeStart, end: rangeEnd } = draft.range;
  const { time, points } = draft.mask;
  if (!Number.isInteger(width) || !Number.isInteger(height) || width <= 0 || height <= 0 ||
      !finite(duration) || duration <= 0 || !finite(rangeStart) || !finite(rangeEnd) ||
      rangeStart < 0 || rangeEnd <= rangeStart || rangeEnd > duration) return false;
  if (!Array.isArray(points) || points.length > 500 ||
      (time !== null && (!finite(time) || time < rangeStart || time > rangeEnd)) ||
      (points.length > 0 && time === null)) return false;
  return points.every((point) => point && finite(point.x) && finite(point.y) &&
    finite(point.radius) && point.x >= 0 && point.x <= 1 &&
    point.y >= 0 && point.y <= 1 && point.radius >= 0.02 && point.radius <= 0.3 &&
    ['include', 'exclude'].includes(point.kind));
}

async function openDraft(file) {
  if (!file) return;
  if (!source.videoWidth || !Number.isFinite(source.duration)) {
    setStatus('Load the original clip before opening its draft.');
    return;
  }
  if (file.size > 131072) {
    setStatus('Draft JSON is too large to open.');
    return;
  }
  try {
    const draft = JSON.parse(await file.text());
    if (!validDraft(draft)) {
      setStatus('Draft JSON is invalid or from an unsupported version.');
      return;
    }
    if (draft.source.width !== source.videoWidth || draft.source.height !== source.videoHeight ||
        Math.abs(draft.source.duration - source.duration) > 0.05 || draft.range.end > source.duration ||
        (draft.mask.time !== null && draft.mask.time > source.duration)) {
      setStatus('Draft dimensions or duration do not match this clip. Load the original used for that draft.');
      return;
    }
    pauseClips();
    start = draft.range.start;
    end = Math.min(source.duration, draft.range.end);
    maskTime = draft.mask.time;
    maskPoints.splice(0, maskPoints.length, ...draft.mask.points);
    clearDifference();
    clearScan();
    selectedPoint = -1;
    activePointer = null;
    showRange();
    seekTo(maskTime ?? start);
    updateMaskReadout();
    redrawMask();
    setStatus('Draft restored. Check that this is the same original clip; duration and dimensions alone cannot prove it.');
  } catch {
    setStatus('Could not read that draft JSON.');
  }
}

function loadClip(kind, url, name, bytes, owned) {
  pauseClips();
  clearDifference();
  clearScan();
  if (clips[kind]?.owned) URL.revokeObjectURL(clips[kind].url);
  clips[kind] = { url, owned };
  if (kind === 'source') {
    resetMask();
    for (const id of ['play-toggle', 'step-back', 'step-forward', 'scrubber', 'range-start', 'range-end', 'use-full', 'save-draft', 'open-draft']) {
      $(id).disabled = true;
    }
    $('detail-size').textContent = sizeLabel(bytes);
  }
  const video = kind === 'source' ? source : result;
  video.src = url;
  video.load();
  updateComparison();
  updateDifferenceAvailability();
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
    for (const id of ['play-toggle', 'step-back', 'step-forward', 'scrubber', 'range-start', 'range-end', 'use-full', 'save-draft', 'open-draft']) {
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
  updateComparison();
}

async function togglePlayback() {
  if (!clips.source) return;
  if (!source.paused) {
    pauseClips();
    return;
  }
  if (source.currentTime >= end - 0.02) seekTo(start);
  clearDifference();
  if (clips.result) seekTo(source.currentTime);
  try {
    await source.play();
    if (clips.result && Number.isFinite(result.duration) && result.currentTime < result.duration - 0.02) {
      await result.play();
    }
    $('play-toggle').textContent = 'Ⅱ';
    $('play-toggle').setAttribute('aria-label', 'Pause selected clip');
    scheduleComparison();
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
  (kind === 'source' ? source : result).addEventListener('loadeddata', () => {
    scheduleComparison();
    updateDifferenceAvailability();
  });
  (kind === 'source' ? source : result).addEventListener('seeked', scheduleComparison);
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
  clearScan();
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
  scheduleComparison();
});

$('compare-wipe').addEventListener('input', () => {
  $('compare-percent').textContent = $('compare-wipe').value + '%';
  scheduleComparison();
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

for (const kind of ['include', 'exclude', 'edit']) {
  $('mask-' + kind).addEventListener('click', () => {
    maskMode = kind;
    for (const mode of ['include', 'exclude', 'edit']) {
      $('mask-' + mode).setAttribute('aria-pressed', String(mode === kind));
    }
    selectedPoint = -1;
    updateMaskReadout();
    redrawMask();
  });
}
$('mask-radius').addEventListener('input', () => {
  $('mask-radius-value').textContent = $('mask-radius').value + '%';
});
$('difference-threshold').addEventListener('input', () => {
  $('difference-threshold-value').textContent = $('difference-threshold').value;
  clearDifference();
  clearScan();
});
$('mask-difference').addEventListener('click', checkDifference);
$('flicker-scan').addEventListener('click', scanNearbyFrames);
$('mask-canvas').addEventListener('pointerdown', markFrame);
$('mask-canvas').addEventListener('pointermove', moveMaskPoint);
$('mask-canvas').addEventListener('pointerup', finishMaskMove);
$('mask-canvas').addEventListener('pointercancel', finishMaskMove);
$('mask-delete').addEventListener('click', deleteMaskPoint);
$('mask-clear').addEventListener('click', resetMask);
$('mask-frame').addEventListener('click', () => {
  if (maskTime === null) return;
  pauseClips();
  seekTo(maskTime);
  redrawMask();
});
$('mask-download').addEventListener('click', () => {
  if (!source.videoWidth || !maskPoints.some((point) => point.kind === 'include')) return;
  buildMask().toBlob((blob) => {
    if (!blob) {
      setStatus('Could not create the mask PNG.');
      return;
    }
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'mask-' + Math.round(maskTime * 1000) + 'ms.png';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setStatus('Downloaded a mask for the marked frame. No video pixels are in the PNG.');
  }, 'image/png');
});
$('save-draft').addEventListener('click', downloadDraft);
$('open-draft').addEventListener('click', () => $('draft-input').click());
$('draft-input').addEventListener('change', async (event) => {
  await openDraft(event.target.files[0]);
  event.target.value = '';
});
source.addEventListener('pause', redrawMask);
source.addEventListener('seeked', redrawMask);
window.addEventListener('resize', redrawMask);

window.addEventListener('beforeunload', () => {
  for (const clip of Object.values(clips)) {
    if (clip?.owned) URL.revokeObjectURL(clip.url);
  }
});

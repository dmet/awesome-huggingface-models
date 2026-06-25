(function () {
  var uploadZone    = document.getElementById('upload-zone');
  var photoInput    = document.getElementById('photo-input');
  var uploadPrompt  = document.getElementById('upload-prompt');
  var photoPreview  = document.getElementById('photo-preview');
  var scheduleEl    = document.getElementById('schedule-notes');
  var weekEl        = document.getElementById('week-phase');
  var analyzeBtn    = document.getElementById('analyze-btn');
  var errorBox      = document.getElementById('error-box');
  var resultWrap    = document.getElementById('result-wrap');
  var resultContent = document.getElementById('result-content');
  var downloadBtn   = document.getElementById('download-btn');

  if (!uploadZone) return; // not on demos page

  var imageBase64    = null;
  var imageMediaType = null;
  var lastResult     = '';

  // Upload zone click
  uploadZone.addEventListener('click', function () { photoInput.click(); });

  photoInput.addEventListener('change', function () {
    if (photoInput.files[0]) handleFile(photoInput.files[0]);
  });

  uploadZone.addEventListener('dragover', function (e) {
    e.preventDefault();
    uploadZone.classList.add('drag-over');
  });
  uploadZone.addEventListener('dragleave', function () {
    uploadZone.classList.remove('drag-over');
  });
  uploadZone.addEventListener('drop', function (e) {
    e.preventDefault();
    uploadZone.classList.remove('drag-over');
    if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  });

  function handleFile(file) {
    if (!file.type.match(/image\/(jpeg|png)/)) {
      showError('Please upload a JPG or PNG image.');
      return;
    }
    resizeAndEncode(file).then(function (result) {
      imageBase64    = result.base64;
      imageMediaType = result.mediaType;
      photoPreview.src = result.preview;
      photoPreview.hidden = false;
      uploadPrompt.hidden = true;
      uploadZone.classList.add('has-image');
    });
  }

  function resizeAndEncode(file) {
    return new Promise(function (resolve) {
      var img = new Image();
      var objectUrl = URL.createObjectURL(file);
      img.onload = function () {
        var MAX = 1280;
        var w = img.naturalWidth;
        var h = img.naturalHeight;
        if (w > MAX || h > MAX) {
          if (w >= h) { h = Math.round((h / w) * MAX); w = MAX; }
          else        { w = Math.round((w / h) * MAX); h = MAX; }
        }
        var canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        canvas.getContext('2d').drawImage(img, 0, 0, w, h);
        URL.revokeObjectURL(objectUrl);
        var mime   = file.type === 'image/png' ? 'image/png' : 'image/jpeg';
        var dataUrl = canvas.toDataURL(mime, 0.88);
        resolve({ base64: dataUrl.split(',')[1], mediaType: mime, preview: dataUrl });
      };
      img.src = objectUrl;
    });
  }

  analyzeBtn.addEventListener('click', function () {
    hideError();
    hideResult();

    var notes = scheduleEl.value.trim();
    var week  = weekEl.value.trim();

    if (!imageBase64) return showError('Upload a jobsite photo first.');
    if (!notes)       return showError('Paste your schedule notes before analyzing.');

    setLoading(true);

    fetch('/.netlify/functions/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image:         imageBase64,
        mediaType:     imageMediaType,
        scheduleNotes: notes,
        weekPhase:     week,
      }),
    })
    .then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) throw new Error(data.error || ('Error ' + res.status));
        return data;
      });
    })
    .then(function (data) {
      lastResult = data.result;
      showResult(lastResult);
    })
    .catch(function (err) {
      showError(err.message || 'Something went wrong. Please try again.');
    })
    .finally(function () {
      setLoading(false);
    });
  });

  downloadBtn.addEventListener('click', function () {
    var blob = new Blob([lastResult], { type: 'text/markdown' });
    var url  = URL.createObjectURL(blob);
    var a    = document.createElement('a');
    a.href = url;
    a.download = 'jobsite-analysis.md';
    a.click();
    URL.revokeObjectURL(url);
  });

  function setLoading(on) {
    analyzeBtn.disabled = on;
    analyzeBtn.innerHTML = on
      ? '<div class="spinner"></div> Analyzing...'
      : 'Analyze Photo Against Schedule';
  }

  function showError(msg) { errorBox.textContent = msg; errorBox.hidden = false; }
  function hideError()    { errorBox.hidden = true; }
  function hideResult()   { resultWrap.hidden = true; }

  function showResult(md) {
    resultContent.innerHTML = renderMarkdown(md);
    resultWrap.hidden = false;
    resultWrap.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function renderMarkdown(md) {
    var s = md
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    s = s
      .replace(/^### (.+)$/gm, '<h3>$1</h3>')
      .replace(/^## (.+)$/gm,  '<h2>$1</h2>')
      .replace(/^# (.+)$/gm,   '<h1>$1</h1>')
      .replace(/\*\*(HIGH)\*\*/g,   '<strong class="severity-high">$1</strong>')
      .replace(/\*\*(MEDIUM)\*\*/g, '<strong class="severity-med">$1</strong>')
      .replace(/\*\*(LOW)\*\*/g,    '<strong class="severity-low">$1</strong>')
      .replace(/\bHIGH\b/g,   '<span class="severity-high">HIGH</span>')
      .replace(/\bMEDIUM\b/g, '<span class="severity-med">MEDIUM</span>')
      .replace(/\bLOW\b/g,    '<span class="severity-low">LOW</span>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g,     '<em>$1</em>')
      .replace(/^[-*] (.+)$/gm,  '<li>$1</li>')
      .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
      .replace(/^---+$/gm, '<hr>');

    s = s.replace(/((?:<li>[\s\S]+?<\/li>\n?)+)/g, '<ul>$1</ul>');

    return s.split(/\n\n+/).map(function (block) {
      var t = block.trim();
      if (!t) return '';
      if (/^<(h[1-6]|ul|ol|hr)[\s>]/.test(t)) return t;
      return '<p>' + t.replace(/\n/g, '<br>') + '</p>';
    }).join('\n');
  }
}());

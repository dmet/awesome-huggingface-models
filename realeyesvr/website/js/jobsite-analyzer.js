(function () {
  var uploadZone   = document.getElementById('upload-zone');
  var photoInput   = document.getElementById('photo-input');
  var uploadPrompt = document.getElementById('upload-prompt');
  var photoPreview = document.getElementById('photo-preview');
  var scheduleEl   = document.getElementById('schedule-notes');
  var weekEl       = document.getElementById('week-phase');
  var apiKeyEl     = document.getElementById('api-key');
  var analyzeBtn   = document.getElementById('analyze-btn');
  var errorBox     = document.getElementById('error-box');
  var resultWrap   = document.getElementById('result-wrap');
  var resultContent= document.getElementById('result-content');
  var downloadBtn  = document.getElementById('download-btn');

  if (!uploadZone) return; // not on demos page

  var imageBase64   = null;
  var imageMediaType= null;
  var lastResult    = '';

  // Restore API key from session storage
  var savedKey = sessionStorage.getItem('or_api_key');
  if (savedKey) apiKeyEl.value = savedKey;
  apiKeyEl.addEventListener('input', function () {
    sessionStorage.setItem('or_api_key', apiKeyEl.value.trim());
  });

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
    imageMediaType = file.type;
    resizeAndEncode(file).then(function (result) {
      imageBase64 = result.base64;
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
        var mime = file.type === 'image/png' ? 'image/png' : 'image/jpeg';
        var dataUrl = canvas.toDataURL(mime, 0.88);
        resolve({ base64: dataUrl.split(',')[1], mediaType: mime, preview: dataUrl });
      };
      img.src = objectUrl;
    });
  }

  analyzeBtn.addEventListener('click', function () {
    hideError();
    hideResult();

    var apiKey = apiKeyEl.value.trim();
    var notes  = scheduleEl.value.trim();
    var week   = weekEl.value.trim();

    if (!apiKey)      return showError('Enter your OpenRouter API key to continue.');
    if (!imageBase64) return showError('Upload a jobsite photo first.');
    if (!notes)       return showError('Paste your schedule notes before analyzing.');

    setLoading(true);

    var weekCtx = week ? 'Current project phase/week: ' + week + '\n' : '';
    var prompt = 'You are a senior construction project manager reviewing a jobsite photo against the project schedule.\n\n'
      + weekCtx
      + 'SCHEDULE NOTES:\n' + notes + '\n\n'
      + 'Analyze the uploaded jobsite photo carefully. Provide a structured report with:\n\n'
      + '1. **WHAT I SEE** — Describe visible work-in-place: materials, structural elements, trades working, site conditions. Be specific about locations if identifiable.\n\n'
      + '2. **SCHEDULE COMPARISON** — For each scheduled item, assess:\n'
      + '   - Is it visible / confirmed in the photo?\n'
      + '   - Does it match the expected status (complete, in progress, not started)?\n'
      + '   - Any discrepancy between schedule and what the photo shows?\n\n'
      + '3. **VARIANCES FLAGGED** — List any schedule vs. reality gaps with severity (HIGH / MEDIUM / LOW).\n\n'
      + '4. **SUMMARY** — One paragraph: overall schedule health based on what you can observe, and recommended follow-up actions.\n\n'
      + 'Be direct and use construction industry language. If the photo does not show enough detail to confirm an item, say so explicitly rather than guessing.';

    fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + apiKey,
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://realeyesvr.com',
        'X-Title': 'RealEyesVR Jobsite Analyzer',
      },
      body: JSON.stringify({
        model: 'qwen/qwen2.5-vl-72b-instruct',
        max_tokens: 1400,
        messages: [{
          role: 'user',
          content: [
            { type: 'image_url', image_url: { url: 'data:' + imageMediaType + ';base64,' + imageBase64 } },
            { type: 'text', text: prompt },
          ],
        }],
      }),
    })
    .then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) {
          var msg = (data.error && data.error.message) || ('API error ' + res.status);
          throw new Error(msg);
        }
        return data;
      });
    })
    .then(function (data) {
      lastResult = data.choices[0].message.content;
      showResult(lastResult);
    })
    .catch(function (err) {
      showError(err.message || 'Something went wrong. Check your API key and try again.');
    })
    .finally(function () {
      setLoading(false);
    });
  });

  downloadBtn.addEventListener('click', function () {
    var blob = new Blob([lastResult], { type: 'text/markdown' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
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
    // Escape HTML to prevent XSS from AI output
    var s = md
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    s = s
      // Headings
      .replace(/^### (.+)$/gm, '<h3>$1</h3>')
      .replace(/^## (.+)$/gm,  '<h2>$1</h2>')
      .replace(/^# (.+)$/gm,   '<h1>$1</h1>')
      // Severity labels before bold (catches **HIGH** and bare HIGH)
      .replace(/\*\*(HIGH)\*\*/g,   '<strong class="severity-high">$1</strong>')
      .replace(/\*\*(MEDIUM)\*\*/g, '<strong class="severity-med">$1</strong>')
      .replace(/\*\*(LOW)\*\*/g,    '<strong class="severity-low">$1</strong>')
      .replace(/\bHIGH\b/g,   '<span class="severity-high">HIGH</span>')
      .replace(/\bMEDIUM\b/g, '<span class="severity-med">MEDIUM</span>')
      .replace(/\bLOW\b/g,    '<span class="severity-low">LOW</span>')
      // Bold and italic
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g,     '<em>$1</em>')
      // List items
      .replace(/^[-*] (.+)$/gm,    '<li>$1</li>')
      .replace(/^\d+\. (.+)$/gm,   '<li>$1</li>')
      // Horizontal rule
      .replace(/^---+$/gm, '<hr>');

    // Wrap consecutive <li> blocks in <ul>
    s = s.replace(/((?:<li>[\s\S]+?<\/li>\n?)+)/g, '<ul>$1</ul>');

    // Paragraphs: split on blank lines
    return s.split(/\n\n+/).map(function (block) {
      var t = block.trim();
      if (!t) return '';
      if (/^<(h[1-6]|ul|ol|hr)[\s>]/.test(t)) return t;
      return '<p>' + t.replace(/\n/g, '<br>') + '</p>';
    }).join('\n');
  }
}());

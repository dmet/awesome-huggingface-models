(function () {
  var list = document.getElementById('resource-list');
  var count = document.getElementById('resource-count');
  if (!list || !count) return;

  fetch('data/resources.json')
    .then(function (response) {
      if (!response.ok) throw new Error('Resource catalog could not be loaded.');
      return response.json();
    })
    .then(function (catalog) {
      count.textContent = catalog.resources.length + ' curated resources · reviewed ' + formatDate(catalog.reviewed);
      list.innerHTML = catalog.resources.map(renderResource).join('');
    })
    .catch(function () {
      count.textContent = 'Catalog unavailable';
      list.innerHTML = '<div class="resource-error"><h2>The resource list could not load.</h2><p>Please try again later.</p></div>';
    });

  function renderResource(resource, index) {
    return '<article class="resource-card">'
      + '<div class="resource-index">' + String(index + 1).padStart(2, '0') + '</div>'
      + '<div class="resource-main">'
      + '<div class="resource-meta"><span>' + escapeHtml(resource.category) + '</span><span>' + escapeHtml(resource.provider) + '</span></div>'
      + '<h2>' + escapeHtml(resource.name) + '</h2>'
      + '<p>' + escapeHtml(resource.description) + '</p>'
      + '<div class="resource-terms"><span>' + escapeHtml(resource.access) + '</span><span>' + escapeHtml(resource.upload_note) + '</span></div>'
      + '</div>'
      + '<a class="resource-open" href="' + escapeHtml(resource.url) + '" target="_blank" rel="noopener noreferrer" aria-label="Open ' + escapeHtml(resource.name) + ' in a new tab">Visit <span aria-hidden="true">↗</span></a>'
      + '</article>';
  }

  function formatDate(value) {
    var parts = value.split('-');
    return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]))
      .toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
}());

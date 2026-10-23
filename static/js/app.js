document.addEventListener('DOMContentLoaded', () => {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content;

  document.querySelector('.tag-filter select')?.addEventListener('change', event => event.currentTarget.form.requestSubmit());
  document.querySelectorAll('form[data-confirm]').forEach(form => form.addEventListener('submit', event => {
    if (!confirm(form.dataset.confirm)) event.preventDefault();
  }));

  const appearanceForm = document.getElementById('appearance-form');
  appearanceForm?.querySelectorAll('select').forEach(select => select.addEventListener('change', () => {
    document.documentElement.dataset[select.name === 'text_size' ? 'textSize' : select.name] = select.value;
    document.getElementById('appearance-preview-note').textContent = 'Preview updated. Save to keep these settings on your other devices.';
  }));

  document.querySelectorAll('.vote-form').forEach(form => form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button');
    button.disabled = true;
    try {
      const response = await fetch(form.action, {method: 'POST', body: new FormData(form), headers: {Accept: 'application/json', 'X-CSRF-Token': csrf}});
      if (response.redirected) { location.href = response.url; return; }
      if (!response.ok) throw Error('Vote could not be saved');
      const result = await response.json();
      const box = form.closest('.vote-box,.comment-actions');
      if (box) {
        box.querySelector('.score').textContent = result.score;
        box.querySelectorAll('.vote-form button').forEach(item => item.setAttribute('aria-pressed', String(Number(item.closest('form').querySelector('[name=value]').value) === result.active)));
      }
    } catch (error) { alert(error.message); }
    finally { button.disabled = false; }
  }));

  document.querySelectorAll('.follow-form,.member-follow-form,.save-form').forEach(form => form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button');
    button.disabled = true;
    try {
      const response = await fetch(form.action, {method: 'POST', body: new FormData(form), headers: {Accept: 'application/json', 'X-CSRF-Token': csrf}});
      if (response.redirected) { location.href = response.url; return; }
      if (!response.ok) throw Error('This action could not be saved. Try again.');
      const result = await response.json();
      const isFollow = form.classList.contains('follow-form') || form.classList.contains('member-follow-form');
      const active = isFollow ? result.following : result.saved;
      button.setAttribute('aria-pressed', String(active));
      button.textContent = isFollow ? (active ? 'Following ✓' : form.classList.contains('member-follow-form') ? 'Follow member' : 'Follow topic') : (active ? '◆ Saved' : '◇ Save');
      if (form.classList.contains('member-follow-form')) {
        button.classList.toggle('primary', !active); button.classList.toggle('secondary', active);
        const total = document.querySelector('.profile-stats a strong');
        if (total) total.textContent = String(Number(total.textContent) + (active ? 1 : -1));
      }
      const feedback = form.querySelector('.action-feedback');
      if (feedback) feedback.textContent = isFollow ? (active ? 'Followed' : 'Unfollowed') : (active ? 'Post saved' : 'Post removed from saved');
    } catch (error) {
      const feedback = form.querySelector('.action-feedback');
      if (feedback) { feedback.classList.remove('sr'); feedback.textContent = error.message; }
    } finally { button.disabled = false; }
  }));

  document.querySelectorAll('.share').forEach(button => button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(button.dataset.url);
      button.textContent = '✓ Link copied';
      setTimeout(() => button.textContent = '↗ Share', 2000);
    } catch { prompt('Copy this link', button.dataset.url); }
  }));
  document.querySelectorAll('.reply-toggle').forEach(button => button.addEventListener('click', () => {
    const form = document.getElementById('reply-' + button.dataset.comment);
    form.classList.toggle('hidden');
    if (!form.classList.contains('hidden')) form.querySelector('textarea').focus();
  }));

  const avatarInput = document.getElementById('avatar');
  const avatarPreview = document.getElementById('avatar-preview');
  let avatarObjectUrl;
  avatarInput?.addEventListener('change', () => {
    if (avatarObjectUrl) URL.revokeObjectURL(avatarObjectUrl);
    const file = avatarInput.files?.[0];
    if (!file) return;
    avatarObjectUrl = URL.createObjectURL(file);
    avatarPreview.replaceChildren();
    const image = document.createElement('img');
    image.src = avatarObjectUrl;
    image.alt = '';
    avatarPreview.append(image);
  });

  const images = document.getElementById('images');
  const imageFields = document.getElementById('image-fields');
  if (images && imageFields) {
    const zone = document.getElementById('upload-zone');
    const status = document.getElementById('upload-status');
    const error = document.getElementById('images-error');
    const selected = [];
    let previewUrls = [];
    const syncFiles = () => {
      const transfer = new DataTransfer();
      selected.forEach(item => transfer.items.add(item.file));
      images.files = transfer.files;
    };
    const renderImages = () => {
      previewUrls.forEach(url => URL.revokeObjectURL(url));
      previewUrls = [];
      imageFields.replaceChildren();
      status.textContent = selected.length ? `${selected.length} of 8 photos selected` : 'No photos selected';
      selected.forEach((item, index) => {
        const card = document.createElement('article'); card.className = 'image-preview-card';
        const thumb = document.createElement('img');
        const url = URL.createObjectURL(item.file); previewUrls.push(url);
        thumb.src = url; thumb.alt = `Preview of photo ${index + 1}`;
        const details = document.createElement('div'); details.className = 'image-preview-details';
        const heading = document.createElement('div'); heading.className = 'image-preview-heading';
        const name = document.createElement('strong'); name.textContent = item.file.name;
        const size = document.createElement('small'); size.textContent = `${(item.file.size / 1048576).toFixed(1)} MB`;
        const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'image-remove';
        remove.textContent = 'Remove'; remove.setAttribute('aria-label', `Remove photo ${index + 1}: ${item.file.name}`);
        remove.addEventListener('click', () => { selected.splice(index, 1); syncFiles(); renderImages(); error.textContent = ''; });
        heading.append(name, size, remove);
        const label = document.createElement('label'); label.textContent = 'Photo label';
        const select = document.createElement('select'); select.name = 'image_label'; select.id = `image-label-${index}`;
        ['Other', 'Before', 'After'].forEach(value => { const option = document.createElement('option'); option.value = value; option.textContent = value; select.append(option); });
        select.value = item.label; select.addEventListener('change', () => { item.label = select.value; }); label.append(select);
        const caption = document.createElement('label'); caption.textContent = 'Caption';
        const input = document.createElement('input'); input.name = 'image_caption'; input.maxLength = 300; input.placeholder = 'Describe what is shown'; input.value = item.caption;
        input.addEventListener('input', () => { item.caption = input.value; }); caption.append(input);
        details.append(heading, label, caption); card.append(thumb, details); imageFields.append(card);
      });
    };
    const addFiles = files => {
      const incoming = Array.from(files);
      const unsupported = incoming.find(file => !['image/jpeg', 'image/png', 'image/webp'].includes(file.type));
      const oversized = incoming.find(file => file.size > 10 * 1048576);
      if (unsupported) { error.textContent = 'Choose JPEG, PNG, or WebP photos only.'; syncFiles(); return; }
      if (oversized) { error.textContent = 'Each photo must be 10 MB or smaller.'; syncFiles(); return; }
      const unique = incoming.filter(file => !selected.some(item => item.file.name === file.name && item.file.size === file.size && item.file.lastModified === file.lastModified));
      if (selected.length + unique.length > 8) { error.textContent = 'Upload no more than eight images.'; syncFiles(); return; }
      unique.forEach(file => selected.push({file, label: 'Other', caption: ''}));
      syncFiles(); renderImages(); error.textContent = '';
    };
    images.addEventListener('change', () => addFiles(images.files));
    zone.addEventListener('dragenter', event => { event.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragover', event => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', event => { if (!zone.contains(event.relatedTarget)) zone.classList.remove('drag-over'); });
    zone.addEventListener('drop', event => { event.preventDefault(); zone.classList.remove('drag-over'); addFiles(event.dataTransfer.files); });
    window.addEventListener('pagehide', () => previewUrls.forEach(url => URL.revokeObjectURL(url)));
  }

  const postForm = document.getElementById('post-form');
  if (postForm) {
    const title = postForm.querySelector('#title');
    const body = postForm.querySelector('#body');
    const counter = postForm.querySelector('#word-count');
    const wordCount = value => (value.match(/[\p{L}\p{N}_]+(?:['’-][\p{L}\p{N}_]+)*/gu) || []).length;
    const updateCount = () => { const count = wordCount(body.value); counter.textContent = `${count} / 1,000 words`; counter.classList.toggle('over-limit', count > 1000); };
    body.addEventListener('input', updateCount); updateCount();
    const initialError = Array.from(postForm.querySelectorAll('[data-field-error]')).find(element => element.textContent.trim());
    if (initialError) requestAnimationFrame(() => initialError.scrollIntoView({block: 'nearest'}));
    const clearError = name => {
      const message = postForm.querySelector(`[data-field-error="${name}"]`);
      if (message) message.textContent = '';
      const input = postForm.querySelector(`[name="${name}"]`);
      input?.removeAttribute('aria-invalid');
    };
    postForm.querySelectorAll('input,textarea,select').forEach(input => {
      const name = input.name === 'tags' ? 'tags' : input.name === 'images' ? 'images' : input.name;
      input.addEventListener(input.type === 'checkbox' || input.type === 'file' ? 'change' : 'input', () => clearError(name));
    });
    const showErrors = errors => {
      postForm.querySelectorAll('[data-field-error]').forEach(element => { element.textContent = ''; });
      let first;
      Object.entries(errors).forEach(([name, message]) => {
        const target = postForm.querySelector(`[data-field-error="${name}"]`);
        const input = postForm.querySelector(`[name="${name}"]`);
        if (!target) return;
        target.textContent = message;
        input?.setAttribute('aria-invalid', 'true');
        first ||= input || target;
      });
      if (first) {
        first.scrollIntoView({block: 'nearest', behavior: 'smooth'});
        first.focus?.({preventScroll: true});
      }
    };
    postForm.addEventListener('submit', async event => {
      event.preventDefault();
      const intent = event.submitter?.value || 'publish';
      const errors = {};
      if (intent === 'publish') {
        const trimmedTitle = title.value.trim(), trimmedBody = body.value.trim();
        if (trimmedTitle.length < 3 || trimmedTitle.length > 120) errors.title = 'Title must be 3–120 characters.';
        if (trimmedBody.length < 10) errors.body = 'Post must be at least 10 characters.';
        else if (wordCount(trimmedBody) > 1000) errors.body = 'Post must be 1,000 words or fewer.';
        else if (trimmedBody.length > 10000) errors.body = 'Post must be 10,000 characters or fewer.';
        if (!postForm.querySelector('[name="tags"]:checked')) errors.tags = 'Choose at least one available topic.';
        if (images?.files.length > 8) errors.images = 'Upload no more than eight images.';
        if (images?.files.length && !postForm.querySelector('[name="photo_consent"]:checked')) errors.photo_consent = 'Confirm photo rights and consent before publishing.';
      } else if (wordCount(body.value.trim()) > 1000 || body.value.trim().length > 10000) {
        errors.body = 'Draft must be 1,000 words and 10,000 characters or fewer.';
      }
      if (Object.keys(errors).length) { showErrors(errors); return; }
      const submitter = event.submitter;
      if (submitter) submitter.disabled = true;
      try {
        const data = new FormData(postForm);
        data.set('intent', intent);
        const response = await fetch(postForm.action || location.href, {method: 'POST', body: data, headers: {Accept: 'application/json'}});
        if (response.redirected) { location.href = response.url; return; }
        if (response.status === 422) { showErrors((await response.json()).errors); return; }
        if (!response.ok) throw Error('Could not save the post. Please try again.');
        location.reload();
      } catch (error) {
        const actions = postForm.querySelector('.form-actions');
        let message = postForm.querySelector('#form-error');
        if (!message) { message = document.createElement('p'); message.id = 'form-error'; message.className = 'field-error'; message.setAttribute('role', 'alert'); actions.after(message); }
        message.textContent = error.message;
      } finally { if (submitter) submitter.disabled = false; }
    });
  }
  const preview = document.getElementById('post-preview');
  document.getElementById('preview-post')?.addEventListener('click', () => {
    document.getElementById('preview-title').textContent = document.getElementById('title').value || 'Untitled post';
    document.getElementById('preview-body').textContent = document.getElementById('body').value || 'No body text yet.';
    preview.showModal();
  });
  document.getElementById('close-preview')?.addEventListener('click', () => preview.close());
  const commentError = document.querySelector('#comment-error, [id^="reply-error-"]');
  if (commentError) requestAnimationFrame(() => commentError.scrollIntoView({block: 'nearest'}));

  const tour = document.getElementById('tutorial');
  const reopen = document.getElementById('reopen-tour');
  if (tour) {
    const steps = [
      {title: 'Your home feed', copy: 'See the latest conversations here. Switch between New and Top, then open a post to read the full discussion.', tip: 'Quick start: find one question you want to follow.', key: 'home'},
      {title: 'Explore topics', copy: 'Browse community topics or search the proposed peptide names. A named discussion does not confirm a Louw product or medical benefit.', tip: 'Quick start: follow a topic that interests you.', key: 'topics'},
      {title: 'Create a post', copy: 'Ask a general question or share your own story. You can add labeled photos with consent; images do not prove a treatment result.', tip: 'Quick start: save a draft before you publish.', key: 'create'},
      {title: 'Build your Following feed', copy: 'Follow topics and members to collect conversations you want to revisit. Your feed will grow as people post.', tip: 'Quick start: explore a topic, then tap Follow topic.', key: 'following'},
      {title: 'Make your profile yours', copy: 'Add a bio and photo, find your posts, and reach saved posts, drafts, settings, and sign out from your profile.', tip: 'You are ready to explore at your own pace.', key: 'profile'}
    ];
    let index = 0, previousFocus = null;
    const card = tour.querySelector('#tour-card'), title = tour.querySelector('#tutorial-title'), copy = tour.querySelector('#tutorial-copy'), tip = tour.querySelector('#tutorial-tip');
    const count = tour.querySelector('#step-count'), back = tour.querySelector('#tour-back'), next = tour.querySelector('#tour-next');
    const ring = tour.querySelector('#tour-target-ring'), arrow = tour.querySelector('#tour-arrow');
    const shades = Object.fromEntries(Array.from(tour.querySelectorAll('[data-tour-shade]')).map(element => [element.dataset.tourShade, element]));
    const visible = element => element && element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden';
    const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));
    function positionTour() {
      const step = steps[index];
      const selector = `[data-tour-target="${step.key}-nav"]`;
      const target = document.querySelector(selector);
      if (!visible(target)) return;
      const rect = target.getBoundingClientRect();
      const width = innerWidth, height = innerHeight, pad = 8;
      const hole = {left: clamp(rect.left - pad, 0, width), top: clamp(rect.top - pad, 0, height), right: clamp(rect.right + pad, 0, width), bottom: clamp(rect.bottom + pad, 0, height)};
      const put = (element, left, top, w, h) => Object.assign(element.style, {left: `${left}px`, top: `${top}px`, width: `${Math.max(0, w)}px`, height: `${Math.max(0, h)}px`});
      put(shades.top, 0, 0, width, hole.top);
      put(shades.left, 0, hole.top, hole.left, hole.bottom - hole.top);
      put(shades.right, hole.right, hole.top, width - hole.right, hole.bottom - hole.top);
      put(shades.bottom, 0, hole.bottom, width, height - hole.bottom);
      put(ring, hole.left, hole.top, hole.right - hole.left, hole.bottom - hole.top);
      const cardWidth = card.offsetWidth, cardHeight = card.offsetHeight, gap = 46, margin = 14;
      const preferred = rect.top > height / 2 ? 'above' : 'below';
      const aboveFits = hole.top - gap - cardHeight >= margin;
      const belowFits = hole.bottom + gap + cardHeight <= height - margin;
      const side = preferred === 'above' && aboveFits ? 'above' : preferred === 'below' && belowFits ? 'below' : aboveFits ? 'above' : belowFits ? 'below' : hole.top > height - hole.bottom ? 'above' : 'below';
      const cardLeft = clamp((rect.left + rect.right - cardWidth) / 2, margin, width - cardWidth - margin);
      const cardTop = clamp(side === 'above' ? hole.top - gap - cardHeight : hole.bottom + gap, margin, height - cardHeight - margin);
      Object.assign(card.style, {left: `${cardLeft}px`, top: `${cardTop}px`});
      const startX = clamp((rect.left + rect.right) / 2, cardLeft + 22, cardLeft + cardWidth - 22);
      const startY = side === 'above' ? cardTop + cardHeight + 4 : cardTop - 4;
      const endX = (rect.left + rect.right) / 2;
      const endY = side === 'above' ? hole.top - 5 : hole.bottom + 5;
      const length = Math.hypot(endX - startX, endY - startY);
      Object.assign(arrow.style, {left: `${startX}px`, top: `${startY}px`, width: `${length}px`, transform: `rotate(${Math.atan2(endY - startY, endX - startX)}rad)`});
    }
    function draw() {
      const step = steps[index];
      title.textContent = step.title; copy.textContent = step.copy; tip.textContent = step.tip;
      count.textContent = `${index + 1} of ${steps.length}`; back.disabled = index === 0; next.textContent = index === steps.length - 1 ? 'Finish' : 'Next';
      tour.querySelectorAll('.tour-progress span').forEach((segment, position) => segment.classList.toggle('complete', position <= index));
      requestAnimationFrame(positionTour);
    }
    function openTour() {
      previousFocus = document.activeElement;
      index = 0; tour.hidden = false; draw(); next.focus({preventScroll: true});
    }
    function finish() {
      tour.hidden = true;
      previousFocus?.focus?.();
      fetch('/tutorial/finish', {method: 'POST', keepalive: true, headers: {Accept: 'application/json', 'X-CSRF-Token': csrf}}).catch(() => {});
    }
    back.addEventListener('click', () => { index = Math.max(0, index - 1); draw(); });
    next.addEventListener('click', () => { if (index === steps.length - 1) finish(); else { index++; draw(); } });
    tour.querySelector('#tour-skip-form').addEventListener('submit', event => { event.preventDefault(); finish(); });
    tour.addEventListener('keydown', event => {
      if (event.key === 'Escape') { event.preventDefault(); finish(); }
      if (event.key !== 'Tab') return;
      const focusable = Array.from(tour.querySelectorAll('button:not(:disabled)')).filter(visible);
      const first = focusable[0], last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    addEventListener('resize', () => { if (!tour.hidden) positionTour(); });
    addEventListener('scroll', () => { if (!tour.hidden) positionTour(); }, {passive: true});
    reopen?.addEventListener('click', openTour);
    if (tour.dataset.firstVisit === 'true') openTour();
  }

  document.querySelector('.header-search button')?.addEventListener('click', event => {
    const form = event.currentTarget.closest('form');
    if (innerWidth < 561 && !form.classList.contains('open')) {
      event.preventDefault(); form.classList.add('open'); form.querySelector('input').focus();
    }
  });
  const topicSearch = document.getElementById('topic-search');
  const topicGroups = Array.from(document.querySelectorAll('.topic-letter-section'));
  const initiallyOpen = new Map(topicGroups.map(group => [group, group.open]));
  topicSearch?.addEventListener('input', () => {
    const term = topicSearch.value.trim().toLocaleLowerCase();
    const cards = Array.from(document.querySelectorAll('[data-topic-card]'));
    let visibleCount = 0;
    cards.forEach(card => {
      card.hidden = !((card.dataset.search || card.textContent).toLocaleLowerCase().includes(term));
      if (!card.hidden) visibleCount++;
    });
    document.querySelectorAll('[data-topic-group]').forEach(group => {
      const hasMatch = !!group.querySelector('[data-topic-card]:not([hidden])');
      group.hidden = term.length > 0 && !hasMatch;
      if (group.matches('details')) group.open = term.length > 0 ? hasMatch : initiallyOpen.get(group);
    });
    document.querySelector('.named-topic-head').hidden = term.length > 0 && !Array.from(document.querySelectorAll('.topic-letter-section')).some(group => !group.hidden);
    document.querySelector('.topics-caveat').hidden = term.length > 0 && !Array.from(document.querySelectorAll('.topic-letter-section')).some(group => !group.hidden);
    document.getElementById('topic-search-empty').hidden = visibleCount > 0 || !term;
  });
});

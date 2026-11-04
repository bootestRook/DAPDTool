import DOMPurify from 'dompurify';

let bridge;
let pendingUploads = 0;
let reportError = () => {};
const remoteRequests = new Map();
const call = (method, ...args) => new Promise(resolve => bridge[method](...args, resolve));
const clean = html => DOMPurify.sanitize(html, {ADD_ATTR: ['data-content-type'],
  FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form'], FORBID_ATTR: ['title']});
const remoteImage = url => new Promise((resolve, reject) => {
  const id = crypto.randomUUID();
  remoteRequests.set(id, {resolve, reject});
  bridge.importRemoteImage(id, url);
});

export function collapseDescription(collapsed) {
  bridge.setCollapsed(collapsed);
}

export async function uploadFile(file) {
  pendingUploads++;
  try {
    if (file.size > 50 * 1024 * 1024) throw new Error('文件超过 50 MB，请选择更小的文件。');
    const data = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.onerror = () => reject(new Error('无法读取文件，请重新选择。'));
      reader.readAsDataURL(file);
    });
    const result = JSON.parse(await call('importFile', data, file.name));
    if (result.error) throw new Error(result.error);
    reportError('');
    return result.url;
  } catch (error) {
    reportError(error.message);
    throw error;
  } finally {
    pendingUploads--;
  }
}

export function connectHost(editor, {onLoad, onError}) {
  reportError = onError;
  const serialize = () => {
    const html = editor.blocksToFullHTML();
    return document.querySelector('.description')?.dataset.mediaLayout === 'row'
      ? '<div data-media-layout="row">' + html + '</div>' : html;
  };
  window.editor = editor;
  window.setContent = (html, readOnly) => {
    try {
      const blocks = editor.tryParseHTMLToBlocks(clean(html));
      editor.replaceBlocks(editor.document, blocks.length ? blocks : [{type: 'paragraph'}]);
      editor.isEditable = !readOnly;
      const rowLayout = new DOMParser().parseFromString(html, 'text/html').querySelector('[data-media-layout="row"]') !== null;
      document.querySelector('.description').dataset.mediaLayout = rowLayout ? 'row' : 'column';
      onLoad(readOnly, rowLayout);
      onError('');
      window.loadedHTML = serialize();
      return true;
    } catch (error) {
      onError(error.message);
      return false;
    }
  };
  window.getContent = () => ({html: serialize(), text: document.querySelector('.bn-editor')?.innerText || '',
    changed: serialize() !== window.loadedHTML, pending: pendingUploads});
  window.insertImage = url => editor.insertInlineContent([{type: 'inlineImage', props: {url, previewWidth: 460}}]);
  window.setPlainText = text => {
    const saved = window.loadedHTML;
    window.setContent('<p>' + text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('\n', '</p><p>') + '</p>', false);
    window.loadedHTML = saved;
  };
  new QWebChannel(qt.webChannelTransport, channel => {
    bridge = channel.objects.bridge;
    bridge.remoteReady.connect((id, raw) => {
      const request = remoteRequests.get(id);
      if (!request) return;
      remoteRequests.delete(id);
      const result = JSON.parse(raw);
      result.error ? request.reject(new Error(result.error)) : request.resolve(result.url);
    });
    bridge.ready();
  });

  const paste = async event => {
    if (!event.target.closest('.bn-editor') || !editor.isEditable || event.clipboardData.files.length) return;
    const html = event.clipboardData.getData('text/html');
    if (!html || !/<img[\s>]/i.test(html)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    pendingUploads++;
    try {
      const doc = new DOMParser().parseFromString(clean(html), 'text/html');
      for (const img of doc.querySelectorAll('img')) {
        const src = img.getAttribute('src') || '';
        if (src.startsWith('https://')) img.src = await remoteImage(src);
        else if (src.startsWith('data:image/')) {
          const blob = await (await fetch(src)).blob();
          img.src = await uploadFile(new File([blob], '粘贴图片.png', {type: blob.type}));
        } else throw new Error('图片链接不受支持，请复制图片本身。');
        if (img.hasAttribute('data-url')) img.dataset.url = img.src;
      }
      editor.pasteHTML(doc.body.innerHTML);
      onError('');
    } catch (error) {
      onError(error.message);
    } finally {
      pendingUploads--;
    }
  };
  document.addEventListener('paste', paste, true);
  const observer = new MutationObserver(() => document.querySelectorAll('[title]').forEach(element => element.removeAttribute('title')));
  observer.observe(document.body, {subtree: true, childList: true, attributes: true, attributeFilter: ['title']});
  return () => {observer.disconnect(); document.removeEventListener('paste', paste, true);};
}

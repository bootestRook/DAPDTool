import {BlockNoteSchema, defaultBlockSpecs, defaultStyleSpecs, defaultInlineContentSpecs,
  createHeadingBlockSpec, createStyleSpec, createInlineContentSpec} from '@blocknote/core';

const fontSize = createStyleSpec({type: 'fontSize', propSchema: 'string'}, {
  render(value) {
    const dom = document.createElement('span');
    dom.style.fontSize = value;
    return {dom, contentDOM: dom};
  },
  parse: element => element.style.fontSize || undefined,
});

function imageDOM({props}) {
  const dom = document.createElement('img');
  dom.src = props.url;
  dom.alt = props.alt;
  dom.dataset.blocknoteInlineImage = 'true';
  dom.style.maxWidth = '100%';
  if (props.previewWidth || props.width) dom.width = props.previewWidth || props.width;
  return {dom};
}

const inlineImage = createInlineContentSpec({type: 'inlineImage', content: 'none', propSchema: {
  url: {default: ''}, alt: {default: ''}, width: {default: 0}, height: {default: 0},
  previewWidth: {default: 0}, uploadId: {default: ''},
}}, {
  render: imageDOM, toExternalHTML: imageDOM, runsBefore: ['image'],
  parse(element) {
    if (element.tagName === 'IMG' && element.dataset.blocknoteInlineImage === 'true') {
      return {url: element.getAttribute('src') || '', alt: element.alt, width: element.width,
        height: element.height, previewWidth: Number(element.dataset.previewWidth) || 0};
    }
  },
});

function mentionDOM({props}) {
  const dom = document.createElement('span');
  dom.dataset.mentionId = props.id;
  dom.dataset.inlineContentType = 'mention';
  dom.textContent = '@' + props.label;
  return {dom};
}

const mention = createInlineContentSpec({type: 'mention', content: 'none',
  propSchema: {id: {default: ''}, label: {default: ''}}}, {
  render: mentionDOM, toExternalHTML: mentionDOM,
  parse(element) {
    if (element.dataset.mentionId) return {id: element.dataset.mentionId, label: element.textContent.replace(/^@/, '')};
  },
});

export const schema = BlockNoteSchema.create({
  blockSpecs: {...defaultBlockSpecs, heading: createHeadingBlockSpec({levels: [1, 2, 3, 4, 5, 6], allowToggleHeadings: true})},
  styleSpecs: {...defaultStyleSpecs, fontSize},
  inlineContentSpecs: {...defaultInlineContentSpecs, inlineImage, mention},
});

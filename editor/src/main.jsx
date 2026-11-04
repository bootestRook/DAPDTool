import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {zh} from '@blocknote/core/locales';
import {filterSuggestionItems, SuggestionMenu} from '@blocknote/core/extensions';
import {AddBlockButton, SideMenu, SideMenuController, SuggestionMenuController,
  getDefaultReactSlashMenuItems, useCreateBlockNote} from '@blocknote/react';
import {BlockNoteView} from '@blocknote/mantine';
import {MantineProvider, Tooltip} from '@mantine/core';
import {RiAddLine, RiArrowDownSLine} from 'react-icons/ri';
import {schema} from './schema';
import {collapseDescription, connectHost, uploadFile} from './host';
import '@blocknote/mantine/style.css';
import './style.css';

const dictionary = {...zh, slash_menu: {...zh.slash_menu, paragraph: {...zh.slash_menu.paragraph, title: '文本'}},
  placeholders: {...zh.placeholders, default: '', emptyDocument: ''}};
const menuOrder = ['paragraph', 'heading', 'heading_2', 'heading_3', 'heading_4', 'heading_5', 'heading_6',
  'numbered_list', 'bullet_list', 'check_list', 'code_block', 'table', 'quote', 'divider',
  'image', 'video', 'audio', 'file', 'toggle_heading', 'toggle_heading_2', 'toggle_heading_3', 'toggle_list', 'emoji'];

function BlockSideMenu() {
  return <SideMenu><AddBlockButton/></SideMenu>;
}

function App() {
  const [readonly, setReadonly] = useState(false);
  const [error, setError] = useState('');
  const [collapsed, setCollapsed] = useState(false);
  const [autoRow, setAutoRow] = useState(false);
  const [empty, setEmpty] = useState(true);
  const editor = useCreateBlockNote({schema, dictionary, uploadFile});

  useEffect(() => {
    const disconnect = connectHost(editor, {
      onLoad(readOnly, rowLayout) {
        setReadonly(readOnly);
        setAutoRow(rowLayout);
        setCollapsed(false);
      },
      onError: setError,
    });
    const sync = () => setEmpty(editor.document.length === 1 && editor.document[0].type === 'paragraph'
      && !editor.document[0].content?.length && !editor.document[0].children?.length);
    const off = editor.onChange(sync);
    return () => {off(); disconnect();};
  }, [editor]);

  const getItems = async query => filterSuggestionItems(
    getDefaultReactSlashMenuItems(editor)
      .sort((a, b) => menuOrder.indexOf(a.key) - menuOrder.indexOf(b.key))
      .map(item => ({...item,
        group: ['image', 'video', 'audio', 'file'].includes(item.key) ? '媒体'
          : item.key.startsWith('toggle_') ? '折叠' : item.key === 'emoji' ? '其他' : '基础',
        icon: <span className="block-icon" data-kind={item.key}>{item.icon}</span>})), query);

  return <MantineProvider theme={{fontFamily: 'Microsoft YaHei UI, sans-serif',
    components: {Tooltip: Tooltip.extend({defaultProps: {disabled: true}})}}}>
    <section className="description" data-empty={empty} data-media-layout={autoRow ? 'row' : 'column'} data-readonly={readonly}>
      <header className="description-header">
        <button className="description-toggle" aria-expanded={!collapsed} aria-controls="description-content"
          onClick={() => {setCollapsed(!collapsed); collapseDescription(!collapsed);}}><RiArrowDownSLine aria-hidden="true"/>描述</button>
        {!readonly && <label className="media-layout">
          <input type="checkbox" role="switch" checked={autoRow} onChange={event => setAutoRow(event.target.checked)}/>
          <span className="switch-track" aria-hidden="true"/><span>媒体自动横排</span>
        </label>}
      </header>
      <div id="description-content" className="description-content" hidden={collapsed}>
        {error && <p className="editor-error" role="alert">{error}</p>}
        {empty && !readonly && <button className="empty-add" aria-label="插入内容" onMouseDown={event => event.preventDefault()}
          onClick={() => {editor.focus(); editor.setTextCursorPosition(editor.document[0]); editor.getExtension(SuggestionMenu).openSuggestionMenu('/');}}>
          <RiAddLine aria-hidden="true"/>
        </button>}
        <BlockNoteView editor={editor} theme="light" editable={!readonly} sideMenu={false} slashMenu={false} linkToolbar={false} attributionTooltip={false}>
          {!readonly && <>
            <SideMenuController sideMenu={BlockSideMenu}/>
            <SuggestionMenuController triggerCharacter="/" getItems={getItems}/>
          </>}
        </BlockNoteView>
      </div>
    </section>
  </MantineProvider>;
}

createRoot(document.getElementById('root')).render(<App/>);

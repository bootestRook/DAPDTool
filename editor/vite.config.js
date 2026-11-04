import {defineConfig} from 'vite';
export default defineConfig({base:'./',build:{outDir:'../dapd_tool/editor_dist',emptyOutDir:true,rollupOptions:{onwarn(warning,warn){if(warning.code!=='MODULE_LEVEL_DIRECTIVE')warn(warning)}}}});

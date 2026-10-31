import { mount } from 'svelte';
import App from './App.svelte';
import './app.css';
import { applyTheme, loadTheme } from './lib/theme';

applyTheme(loadTheme()); // a module script, never an inline one: the CSP forbids inline scripts

mount(App, { target: document.getElementById('app')! });

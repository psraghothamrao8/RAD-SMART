/**
 * Standalone harness, NOT the federation entrypoint: the host only ever imports
 * `./manifest`. This page exists so `vite preview` serves something.
 */
const root = document.getElementById("root");
if (root) root.textContent = "RAD-SMART plugin for CARE: load it through care_fe (REACT_ENABLED_APPS).";

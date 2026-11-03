// Browser stub for Node-only optional dependencies. pdf.js requires
// `@napi-rs/canvas` from its NodeCanvasFactory, which is unreachable in a
// browser build but still gets resolved by the CommonJS plugin. The real
// package ships a native `.node` binding that cannot be bundled.
export {};

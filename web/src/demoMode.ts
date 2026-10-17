// A build-time switch: a URL parameter can never turn a real deployment into a demo.
export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true'

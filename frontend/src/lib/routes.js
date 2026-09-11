export const HAS_PUBLIC_HOME = import.meta.env.VITE_PORTFYL_EDITION === "cloud";
export const TRACKER_HOME = HAS_PUBLIC_HOME ? "/dashboard" : "/";

// Local UI is the default. API integration is an explicit build-time opt-in.
export const localUI = process.env.NEXT_PUBLIC_DATA_SOURCE !== "api";

import { createContext, useContext } from "react";
import { NAV_GROUPS } from "./navigation";

// The edition-aware navigation, provided by AppShell so deep components (the
// Preferences page, which lets the user pick the phone bottom bar) can read the
// same page list the sidebar shows without prop drilling. Outside an AppShell
// (tests, demo shell) it falls back to the shared base navigation.
export const NavGroupsContext = createContext(NAV_GROUPS);

export function useNavGroups() {
  return useContext(NavGroupsContext);
}

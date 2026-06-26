import { createContext, useContext, useState } from "react";
import { Me } from "../api";

const MeContext = createContext<Me | null>(null);

export function MeProvider({ initial, children }: { initial: Me | null; children: React.ReactNode }) {
  const [me] = useState<Me | null>(initial);
  return <MeContext.Provider value={me}>{children}</MeContext.Provider>;
}

export function useMe(): Me | null {
  return useContext(MeContext);
}

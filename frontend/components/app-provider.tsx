"use client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { localUI } from "@/lib/data-source";
import { configureAuthorization } from "@/lib/api/client";
import {
  authConfigured,
  getAuthManager,
  signOut as endSession,
  signIn,
  canRestoreSession,
  forgetSession,
  rememberSession,
} from "@/lib/auth/cognito";
import {
  clearDevHandle,
  devAuthEnabled,
  devHandle,
  devSignInError,
  setDevHandle,
} from "@/lib/auth/dev";
import { photoCache } from "@/lib/api/photo-cache";
import { services } from "@/lib/api/services";
import { emptyState } from "@/lib/api/types";
import type {
  AppState,
  Domain,
  HealthRecord,
  NewPetInput,
  Pet,
  PetInput,
  Profile,
  RecordInput,
  ReminderUpdate,
  ResourceStatus,
  ShippingInput,
} from "@/lib/api/types";
type AuthStatus = "loading" | "signed-out" | "signed-in" | "error";
const domains: Domain[] = [
  "catalogue",
  "facilities",
  "pets",
  "reminders",
  "cart",
  "orders",
  "merchant",
];
const initialStatus = () =>
  Object.fromEntries(
    domains.map((d) => [d, { loading: true, error: null, loaded: false }]),
  ) as Record<Domain, ResourceStatus>;
type Context = {
  state: AppState;
  ready: boolean;
  authStatus: AuthStatus;
  authError: string | null;
  resources: Record<Domain, ResourceStatus>;
  pending: string[];
  notice: string;
  notify: (text: string) => void;
  signOut: () => Promise<void>;
  /** LOCAL DEVELOPMENT ONLY: sign in as a seeded user (see lib/auth/dev.ts). */
  signInDev: (handle: string) => Promise<void>;
  retryAuth: () => void;
  refresh: (domain: Domain) => Promise<void>;
  actions: {
    createPet: (input: NewPetInput) => Promise<string>;
    updatePet: (id: string, input: PetInput) => Promise<void>;
    deletePet: (id: string) => Promise<void>;
    uploadPetPhoto: (id: string, file: File) => Promise<void>;
    removePetPhoto: (id: string) => Promise<void>;
    addRecord: (
      pet: string,
      input: Parameters<typeof services.addRecord>[1],
    ) => Promise<void>;
    updateRecord: (
      pet: string,
      record: string,
      input: Partial<RecordInput>,
    ) => Promise<void>;
    deleteRecord: (pet: string, record: string) => Promise<void>;
    createReminder: (
      input: Parameters<typeof services.createReminder>[0],
    ) => Promise<void>;
    setReminder: (id: string, done: boolean) => Promise<void>;
    updateReminder: (id: string, input: ReminderUpdate) => Promise<void>;
    deleteReminder: (id: string) => Promise<void>;
    addCart: (id: string) => Promise<void>;
    updateCart: (id: string, quantity: number) => Promise<void>;
    removeCart: (id: string) => Promise<void>;
    checkout: (input: ShippingInput, key: string) => Promise<string>;
    updateProduct: (id: string, price: number, stock: number) => Promise<void>;
    updateMerchantOrder: (id: string, status: string) => Promise<void>;
  };
};
const AppContext = createContext<Context | null>(null);
export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AppState>(emptyState);
  const stateRef = useRef(state);
  const [resources, setResources] = useState(initialStatus);
  const [authStatus, setAuthStatus] = useState<AuthStatus>("loading");
  const [authError, setAuthError] = useState<string | null>(null);
  const [notice, notify] = useState("");
  const [pending, setPending] = useState<string[]>([]);
  const generation = useRef(0);
  const locks = useRef(new Set<string>());
  const versions = useRef(new Map<Domain, number>());
  // True while an explicit development sign-in runs; its form reports errors.
  const signingInDev = useRef(false);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);
  const resetPrivate = useCallback(() => {
    setResources((s) => ({
      ...s,
      ...Object.fromEntries(
        (["pets", "reminders", "cart", "orders", "merchant"] as Domain[]).map(
          (domain) => [domain, { loading: true, error: null, loaded: false }],
        ),
      ),
    }));
    setState((s) => ({
      ...emptyState(),
      products: s.products,
      categories: s.categories,
      merchants: s.merchants,
      facilities: s.facilities,
    }));
  }, []);
  const clearPrivate = useCallback(() => {
    generation.current++;
    forgetSession();
    // Downloaded photos belong to the previous account.
    photoCache.clear();
    resetPrivate();
    setAuthStatus("signed-out");
  }, [resetPrivate]);
  const refresh = useCallback(async (domain: Domain) => {
    const epoch = generation.current;
    const version = (versions.current.get(domain) || 0) + 1;
    versions.current.set(domain, version);
    setResources((s) => ({
      ...s,
      [domain]: { ...s[domain], loading: true, error: null },
    }));
    try {
      let patch: Partial<AppState> = {};
      const current = stateRef.current;
      if (domain === "catalogue") patch = await services.catalogue();
      else if (domain === "facilities")
        patch = { facilities: await services.facilities() };
      else if (domain === "pets") patch = { pets: await services.pets() };
      else if (domain === "reminders")
        patch = { reminders: await services.reminders() };
      else if (domain === "cart")
        patch = {
          cart: await services.cart(current.categories, current.merchants),
        };
      else if (domain === "orders") patch = { orders: await services.orders() };
      else if (domain === "merchant") {
        const [products, orders] = await Promise.all([
          services.merchantProducts(current.categories, current.merchants),
          services.merchantOrders(),
        ]);
        patch = { merchant_products: products, merchant_orders: orders };
      }
      if (
        (domain === "catalogue" ||
          domain === "facilities" ||
          epoch === generation.current) &&
        versions.current.get(domain) === version
      ) {
        setState((s) => ({ ...s, ...patch }));
        setResources((s) => ({
          ...s,
          [domain]: { loading: false, error: null, loaded: true },
        }));
      }
    } catch (error) {
      if (
        (domain === "catalogue" ||
          domain === "facilities" ||
          epoch === generation.current) &&
        versions.current.get(domain) === version
      )
        setResources((s) => ({
          ...s,
          [domain]: {
            loaded: s[domain].loaded,
            loading: false,
            error:
              error instanceof Error
                ? error.message
                : "Unable to load this page.",
          },
        }));
    }
  }, []);
  const loadIdentity = useCallback(async (): Promise<AuthStatus> => {
    if (localUI) {
      const profile = await services.me();
      setState((s) => ({ ...s, profile, role: "owner" }));
      setAuthStatus("signed-in");
      return "signed-in";
    }
    if (devAuthEnabled()) {
      const epoch = ++generation.current;
      // Read now, so a superseded call cannot act for a later sign-in.
      const explicit = signingInDev.current;
      setAuthError(null);
      resetPrivate();
      if (!devHandle()) {
        setAuthStatus("signed-out");
        return "signed-out";
      }
      setAuthStatus("loading");
      let profile: Profile;
      try {
        profile = await services.me();
      } catch (error) {
        if (explicit) {
          clearPrivate();
          clearDevHandle();
          throw new Error(devSignInError(error));
        }
        if (epoch !== generation.current) return "loading";
        setAuthError(devSignInError(error));
        setAuthStatus("error");
        return "error";
      }
      if (epoch !== generation.current) return "loading";
      const role = profile.groups.includes("merchant") ? "merchant" : "owner";
      setState((s) => ({
        ...emptyState(),
        products: s.products,
        categories: s.categories,
        merchants: s.merchants,
        facilities: s.facilities,
        role,
        profile,
      }));
      setAuthStatus("signed-in");
      return "signed-in";
    }
    if (!authConfigured()) {
      setAuthStatus("signed-out");
      return "signed-out";
    }
    const epoch = ++generation.current;
    setAuthStatus("loading");
    setAuthError(null);
    resetPrivate();
    try {
      const user = await getAuthManager().getUser();
      if (epoch !== generation.current) return "loading";
      if (!user || user.expired) {
        if (
          canRestoreSession() &&
          !window.location.pathname.startsWith("/auth/")
        ) {
          await signIn(
            window.location.pathname.startsWith("/login")
              ? new URL(window.location.href).searchParams.get("next") ||
                  "/pets/"
              : window.location.pathname + window.location.search,
            true,
          );
          return "loading";
        }
        clearPrivate();
        return "signed-out";
      }
      const profile = await services.me();
      if (epoch !== generation.current) return "loading";
      const role = profile.groups.includes("merchant") ? "merchant" : "owner";
      setState((s) => ({
        ...emptyState(),
        products: s.products,
        categories: s.categories,
        merchants: s.merchants,
        facilities: s.facilities,
        role,
        profile,
      }));
      setAuthStatus("signed-in");
      return "signed-in";
    } catch (error) {
      if (epoch !== generation.current) return "loading";
      setAuthError(
        error instanceof Error ? error.message : "Unable to load your account.",
      );
      setAuthStatus("error");
      return "error";
    }
  }, [clearPrivate, resetPrivate]);
  useEffect(() => {
    configureAuthorization(
      // The full Authorization header value, or null when signed out.
      async () => {
        if (devAuthEnabled()) {
          const handle = devHandle();
          return handle ? `Dev ${handle}` : null;
        }
        if (!authConfigured()) return null;
        const user = await getAuthManager().getUser();
        return user && !user.expired && user.access_token
          ? `Bearer ${user.access_token}`
          : null;
      },
      () => {
        clearPrivate();
        if (devAuthEnabled()) {
          clearDevHandle();
          // During an explicit sign-in the login form reports the failure.
          if (signingInDev.current) return;
        } else if (authConfigured()) void getAuthManager().removeUser();
        notify("Your session has ended. Sign in to continue.");
      },
    );
    queueMicrotask(() => {
      void refresh("catalogue");
      void refresh("facilities");
      void loadIdentity();
    });
    if (localUI || devAuthEnabled() || !authConfigured()) return;
    let manager: ReturnType<typeof getAuthManager>;
    try {
      manager = getAuthManager();
    } catch (error) {
      queueMicrotask(() => {
        setAuthError(
          error instanceof Error ? error.message : "Sign-in is unavailable.",
        );
        setAuthStatus("error");
      });
      return;
    }
    const loaded = () => {
      rememberSession();
      void loadIdentity();
    };
    const expired = () => {
      clearPrivate();
      notify("Your session has ended. Sign in to continue.");
    };
    manager.events.addUserLoaded(loaded);
    manager.events.addUserUnloaded(clearPrivate);
    manager.events.addAccessTokenExpired(expired);
    manager.events.addSilentRenewError(expired);
    return () => {
      manager.events.removeUserLoaded(loaded);
      manager.events.removeUserUnloaded(clearPrivate);
      manager.events.removeAccessTokenExpired(expired);
      manager.events.removeSilentRenewError(expired);
    };
  }, [clearPrivate, loadIdentity, refresh]);
  useEffect(() => {
    if (authStatus !== "signed-in") return;
    void refresh("pets");
    void refresh("reminders");
    void refresh("cart");
    void refresh("orders");
    if (localUI || state.role === "merchant") void refresh("merchant");
  }, [authStatus, state.role, refresh]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => notify(""), 6000);
    return () => clearTimeout(timer);
  }, [notice]);
  async function perform<T>(
    key: string,
    operation: (ensureCurrent: () => void) => Promise<T>,
  ): Promise<T> {
    if (locks.current.has(key))
      throw new Error("This action is already in progress.");
    locks.current.add(key);
    setPending([...locks.current]);
    const epoch = generation.current;
    const ensureCurrent = () => {
      if (epoch !== generation.current)
        throw new Error("Your session changed. Reload the page to continue.");
    };
    try {
      return await operation(ensureCurrent);
    } finally {
      locks.current.delete(key);
      setPending([...locks.current]);
    }
  }
  const replacePet = (id: string, update: (p: Pet) => Pet) =>
    setState((s) => ({
      ...s,
      pets: s.pets.map((p) => (p.id === id ? update(p) : p)),
    }));
  const setRecords = (petId: string, records: HealthRecord[]) =>
    replacePet(petId, (p) => ({ ...p, records }));
  const actions: Context["actions"] = {
    createPet: (input) =>
      perform("pet:create", async (guard) => {
        const p = await services.createPet(input);
        guard();
        setState((s) => ({ ...s, pets: [...s.pets, p] }));
        notify("Pet passport created.");
        return p.id;
      }),
    updatePet: (id, input) =>
      perform(`pet:${id}`, async (guard) => {
        const row = await services.updatePet(id, input);
        guard();
        replacePet(id, (p) => ({ ...row, records: p.records }));
        notify("Pet passport updated.");
      }),
    deletePet: (id) =>
      perform(`pet:${id}`, async (guard) => {
        await services.deletePet(id);
        guard();
        photoCache.forget(id);
        await Promise.all([refresh("pets"), refresh("reminders")]);
        notify("Pet passport deleted.");
      }),
    uploadPetPhoto: (id, file) =>
      perform(`pet-photo:${id}`, async (guard) => {
        const row = await services.uploadPetPhoto(id, file);
        guard();
        replacePet(id, (p) => ({ ...row, records: p.records }));
        notify("Photo updated.");
      }),
    removePetPhoto: (id) =>
      perform(`pet-photo:${id}`, async (guard) => {
        await services.removePetPhoto(id);
        guard();
        photoCache.forget(id);
        replacePet(id, (p) => ({ ...p, photo_url: null, photo_version: null }));
        notify("Photo removed.");
      }),
    addRecord: (id, input) =>
      perform(`record:${id}`, async (guard) => {
        await services.addRecord(id, input);
        guard();
        // The backend never creates reminders from a record, so only this
        // pet's records need reloading.
        const records = await services.records(id);
        guard();
        setRecords(id, records);
        notify("Care record saved.");
      }),
    updateRecord: (petId, recordId, input) =>
      perform(`record:${petId}:${recordId}`, async (guard) => {
        await services.updateRecord(petId, recordId, input);
        guard();
        const records = await services.records(petId);
        guard();
        setRecords(petId, records);
        notify("Care record updated.");
      }),
    deleteRecord: (petId, recordId) =>
      perform(`record:${petId}:${recordId}`, async (guard) => {
        await services.deleteRecord(petId, recordId);
        guard();
        const records = await services.records(petId);
        guard();
        setRecords(petId, records);
        await refresh("reminders");
        notify("Care record deleted.");
      }),
    createReminder: (input) =>
      perform("reminder:create", async (guard) => {
        await services.createReminder(input);
        guard();
        await refresh("reminders");
        notify("Care reminder created.");
      }),
    setReminder: (id, done) =>
      perform(`reminder:${id}`, async (guard) => {
        await services.setReminder(id, done);
        guard();
        await refresh("reminders");
      }),
    updateReminder: (id, input) =>
      perform(`reminder:${id}`, async (guard) => {
        await services.updateReminder(id, input);
        guard();
        await refresh("reminders");
        notify("Reminder updated.");
      }),
    deleteReminder: (id) =>
      perform(`reminder:${id}`, async (guard) => {
        await services.deleteReminder(id);
        guard();
        await refresh("reminders");
        notify("Reminder deleted.");
      }),
    addCart: (id) =>
      perform(`cart:${id}`, async (guard) => {
        await services.addCart(id);
        guard();
        await refresh("cart");
        notify("Product added to your basket.");
      }),
    updateCart: (id, quantity) =>
      perform(`cart:${id}`, async (guard) => {
        await services.updateCart(id, quantity);
        guard();
        await refresh("cart");
      }),
    removeCart: (id) =>
      perform(`cart:${id}`, async (guard) => {
        await services.removeCart(id);
        guard();
        await refresh("cart");
        notify("Item removed from your basket.");
      }),
    checkout: (input, key) =>
      perform("checkout", async (guard) => {
        const order = await services.checkout(input, key);
        guard();
        setState((s) => ({
          ...s,
          orders: [order, ...s.orders.filter((o) => o.id !== order.id)],
        }));
        await refresh("cart");
        if (localUI)
          await Promise.all([refresh("catalogue"), refresh("merchant")]);
        return order.id;
      }),
    updateProduct: (id, price, stock) =>
      perform(`product:${id}`, async (guard) => {
        await services.updateProduct(id, price, stock);
        guard();
        await Promise.all([refresh("merchant"), refresh("catalogue")]);
        notify("Product updated.");
      }),
    updateMerchantOrder: (id, status) =>
      perform(`order:${id}`, async (guard) => {
        await services.updateMerchantOrder(id, status);
        guard();
        await refresh("merchant");
        if (localUI) await refresh("orders");
        notify("Order status updated.");
      }),
  };
  return (
    <AppContext.Provider
      value={{
        state,
        ready: authStatus !== "loading",
        authStatus,
        authError,
        resources,
        pending,
        notice,
        notify,
        signOut: async () => {
          clearPrivate();
          if (devAuthEnabled()) {
            clearDevHandle();
            return;
          }
          await endSession();
        },
        signInDev: async (handle) => {
          signingInDev.current = true;
          try {
            // Switching users in the same tab skips clearPrivate().
            photoCache.clear();
            setDevHandle(handle);
            const status = await loadIdentity();
            if (status !== "signed-in")
              throw new Error("Development sign-in failed. Please try again.");
          } finally {
            signingInDev.current = false;
          }
        },
        retryAuth: () => {
          void loadIdentity();
        },
        refresh,
        actions,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}
export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error("AppProvider is required");
  return value;
}

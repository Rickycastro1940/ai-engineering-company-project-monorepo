/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly NEXT_PUBLIC_INVENTORY_API_URL?: string;
  readonly VITE_INVENTORY_API_URL?: string;
  readonly VITE_API_PROXY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

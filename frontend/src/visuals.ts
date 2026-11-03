import {
  BrickWallFire, Cable, EthernetPort, Gamepad2, IdCard, Router, ShoppingCart, Tv, UserCog, Waypoints, Wifi,
  Boxes, Briefcase, Clapperboard, Cloud, ServerCog, Database, FileArchive, Folder, Globe, HardDrive, KeyRound, Landmark, Laptop, type LucideIcon,
  Mail, MapPin, Monitor, Network, Package, Server, Share2, Smartphone, Tablet, Terminal, UserRound, Usb, Vault,
} from "lucide-react";
import type { Catalog } from "./types";

export const NODE_ICONS: Record<string, LucideIcon> = {
  desktop: Monitor,
  laptop: Laptop,
  tablet: Tablet,
  smartphone: Smartphone,
  smart_tv: Tv,
  modem: Cable,
  router: Router,
  firewall: BrickWallFire,
  switch: EthernetPort,
  wifi: Wifi,
  local_server_account: UserCog,
  work_account: Briefcase,
  entertainment_account: Clapperboard,
  infrastructure_account: ServerCog,
  vpn_account: Waypoints,
  gaming_account: Gamepad2,
  shopping_account: ShoppingCart,
  government_account: IdCard,
  usb_drive: Usb,
  nas_server: Server,
  hardware_key: KeyRound,
  cloud: Cloud,
  local_network: Network,
  offsite: MapPin,
  os: Terminal,
  application: Package,
  app_group: Boxes,
  password_manager: Vault,
  email_account: Mail,
  financial_account: Landmark,
  social_account: Share2,
  cloud_storage: HardDrive,
  online_account: UserRound,
  folder: Folder,
  database: Database,
  backup: FileArchive,
};

export const FALLBACK_ICON: LucideIcon = Briefcase;
export const WEB_ICON: LucideIcon = Globe;

export const CATEGORY_COLORS: Record<string, string> = {
  hardware: "#38bdf8",
  network: "#a3e635",
  location: "#a78bfa",
  software: "#34d399",
  identity: "#fbbf24",
  data: "#f472b6",
};

export const RELATION_COLORS: Record<string, string> = {
  auth: "#fbbf24",
  stack: "#38bdf8",
  network: "#a3e635",
  data: "#f472b6",
  other: "#7c8a9e",
};

export function categoryOf(catalog: Catalog, type: string): string {
  return Object.entries(catalog.categories).find(([, category]) => type in category.types)?.[0] ?? "hardware";
}

export function typeLabel(catalog: Catalog, type: string): string {
  return catalog.categories[categoryOf(catalog, type)]?.types[type] ?? type;
}

export function usesEmail(catalog: Catalog, type: string): boolean {
  return catalog.fields[type]?.includes("email") ?? false;
}

export const LOSS_MODE_LABELS: Record<string, string> = {
  required: "Required: losing it causes failure",
  alternative: "Alternative: fails only if all alternatives are lost",
  backup: "Backup copy: never fails on its own",
  network: "Network: goes offline, but what relies on it keeps working",
  none: "None: doesn't affect availability",
};

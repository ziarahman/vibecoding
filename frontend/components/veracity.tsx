import {
  BadgeCheck,
  CircleHelp,
  ShieldAlert,
  Clock,
  type LucideIcon,
} from "lucide-react";
import type { VeracityStatus } from "@/lib/types";
import { Badge, type BadgeProps } from "@/components/ui/badge";

interface VeracityMeta {
  label: string;
  variant: NonNullable<BadgeProps["variant"]>;
  icon: LucideIcon;
  /** Tailwind text color for meters / accents. */
  accent: string;
  bar: string;
}

export const VERACITY: Record<VeracityStatus, VeracityMeta> = {
  VERIFIED: {
    label: "Verified",
    variant: "success",
    icon: BadgeCheck,
    accent: "text-[hsl(142_71%_55%)]",
    bar: "bg-[hsl(142_71%_45%)]",
  },
  SPECULATIVE: {
    label: "Speculative",
    variant: "warning",
    icon: CircleHelp,
    accent: "text-[hsl(38_92%_60%)]",
    bar: "bg-[hsl(38_92%_50%)]",
  },
  CONTRADICTED: {
    label: "Contradicted",
    variant: "danger",
    icon: ShieldAlert,
    accent: "text-[hsl(0_84%_68%)]",
    bar: "bg-[hsl(0_84%_60%)]",
  },
  PENDING: {
    label: "Pending",
    variant: "muted",
    icon: Clock,
    accent: "text-muted-foreground",
    bar: "bg-muted-foreground",
  },
};

export function VeracityBadge({ status }: { status: VeracityStatus }) {
  const meta = VERACITY[status] ?? VERACITY.PENDING;
  const Icon = meta.icon;
  return (
    <Badge variant={meta.variant}>
      <Icon className="h-3.5 w-3.5" />
      {meta.label}
    </Badge>
  );
}

const CATEGORY_LABELS: Record<string, string> = {
  S1_FILING: "S-1 Filing",
  PRICE_RANGE: "Price Range",
  ROADSHOW: "Roadshow",
  PRICING: "Pricing",
  LISTING: "Listing",
  WITHDRAWAL: "Withdrawal",
  RUMOR: "Rumor",
  OTHER: "Other",
};

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category;
}

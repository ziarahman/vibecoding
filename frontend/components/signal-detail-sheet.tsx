"use client";

/**
 * signal-detail-sheet.tsx
 * The slide-out drill-down for a single IPO signal. Three deep-dive tabs:
 *   1. Overview     — key/value layout of extracted metrics
 *   2. Audit Trail  — chronological timeline of verification evidence
 *   3. AI Judgment  — the adjudicator's reasoning + confidence meter
 */

import * as React from "react";
import {
  ArrowUpRight,
  Building2,
  CalendarClock,
  CheckCircle2,
  ExternalLink,
  FileText,
  Gavel,
  Landmark,
  Quote,
  ScrollText,
  ShieldCheck,
  TrendingUp,
  XCircle,
} from "lucide-react";
import type { EvidenceItem, Signal } from "@/lib/types";
import {
  formatDateTime,
  formatPriceRange,
  formatShares,
  formatUsd,
  timeAgo,
} from "@/lib/utils";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { VeracityBadge, VERACITY, categoryLabel } from "@/components/veracity";

interface SignalDetailSheetProps {
  signal: Signal | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SignalDetailSheet({
  signal,
  open,
  onOpenChange,
}: SignalDetailSheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto p-0 scrollbar-thin sm:max-w-xl"
      >
        {signal ? (
          <SignalDetailBody signal={signal} />
        ) : (
          <div className="p-6 text-sm text-muted-foreground">
            No signal selected.
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

function SignalDetailBody({ signal }: { signal: Signal }) {
  const meta = VERACITY[signal.status] ?? VERACITY.PENDING;
  return (
    <>
      <SheetHeader className="bg-gradient-to-b from-muted/40 to-transparent">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <SheetTitle className="flex items-center gap-2 text-xl">
              {signal.company_name}
              {signal.ticker && (
                <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
                  {signal.ticker}
                </span>
              )}
            </SheetTitle>
            <SheetDescription className="max-w-md">
              {signal.headline_claim}
            </SheetDescription>
          </div>
          <VeracityBadge status={signal.status} />
        </div>
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Badge variant="secondary">{categoryLabel(signal.category)}</Badge>
          {signal.exchange && (
            <Badge variant="outline" className="gap-1">
              <Landmark className="h-3 w-3" />
              {signal.exchange}
            </Badge>
          )}
          <span className="text-xs text-muted-foreground">
            Updated {timeAgo(signal.updated_at)}
          </span>
        </div>
      </SheetHeader>

      <div className="p-6">
        <Tabs defaultValue="overview">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="overview">
              <FileText className="h-4 w-4" /> Overview
            </TabsTrigger>
            <TabsTrigger value="audit">
              <ScrollText className="h-4 w-4" /> Audit Trail
            </TabsTrigger>
            <TabsTrigger value="judgment">
              <Gavel className="h-4 w-4" /> AI Judgment
            </TabsTrigger>
          </TabsList>

          {/* ---------------- Tab 1: Overview ---------------- */}
          <TabsContent value="overview">
            <OverviewTab signal={signal} />
          </TabsContent>

          {/* ---------------- Tab 2: Audit Trail ---------------- */}
          <TabsContent value="audit">
            <AuditTrailTab evidence={signal.evidence} sourceUrl={signal.source_url} />
          </TabsContent>

          {/* ---------------- Tab 3: AI Judgment ---------------- */}
          <TabsContent value="judgment">
            <JudgmentTab signal={signal} accentColor={meta.accent} barColor={meta.bar} />
          </TabsContent>
        </Tabs>
      </div>
    </>
  );
}

/* ----------------------------------------------------------------------- */
/* Overview                                                                 */
/* ----------------------------------------------------------------------- */
function OverviewTab({ signal }: { signal: Signal }) {
  const rows: { icon: typeof Building2; label: string; value: string }[] = [
    { icon: Building2, label: "Company", value: signal.company_name },
    { icon: TrendingUp, label: "Ticker", value: signal.ticker || "—" },
    { icon: Landmark, label: "Exchange", value: signal.exchange || "—" },
    { icon: ShieldCheck, label: "Category", value: categoryLabel(signal.category) },
    { icon: TrendingUp, label: "Valuation", value: formatUsd(signal.valuation_usd) },
    {
      icon: TrendingUp,
      label: "Price Range",
      value: formatPriceRange(signal.price_range_low, signal.price_range_high),
    },
    { icon: TrendingUp, label: "Shares Offered", value: formatShares(signal.shares_offered) },
    {
      icon: CalendarClock,
      label: "Projected Date",
      value: signal.projected_date || "—",
    },
  ];

  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border">
        {rows.map((r) => {
          const Icon = r.icon;
          return (
            <div key={r.label} className="bg-card p-3">
              <dt className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-muted-foreground">
                <Icon className="h-3.5 w-3.5" /> {r.label}
              </dt>
              <dd className="mt-1 font-medium tabular-nums">{r.value}</dd>
            </div>
          );
        })}
      </dl>

      {signal.raw_quote && (
        <figure className="rounded-lg border border-border bg-muted/30 p-4">
          <Quote className="h-4 w-4 text-muted-foreground" />
          <blockquote className="mt-2 text-sm italic text-foreground/90">
            “{signal.raw_quote}”
          </blockquote>
        </figure>
      )}

      {signal.source_url && (
        <a
          href={signal.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
        >
          <ExternalLink className="h-4 w-4" />
          {signal.source_name || "View original source"}
        </a>
      )}
    </div>
  );
}

/* ----------------------------------------------------------------------- */
/* Audit Trail                                                              */
/* ----------------------------------------------------------------------- */
function AuditTrailTab({
  evidence,
  sourceUrl,
}: {
  evidence: EvidenceItem[];
  sourceUrl?: string | null;
}) {
  if (!evidence || evidence.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
        No verification evidence was recorded for this signal.
      </div>
    );
  }

  const sorted = [...evidence].sort(
    (a, b) =>
      new Date(a.retrieved_at).getTime() - new Date(b.retrieved_at).getTime()
  );

  return (
    <ol className="relative space-y-4 border-l border-border pl-6">
      {sorted.map((e, i) => {
        const Icon = e.supports_claim ? CheckCircle2 : XCircle;
        const color = e.supports_claim
          ? "text-[hsl(142_71%_55%)]"
          : "text-[hsl(0_84%_68%)]";
        return (
          <li key={i} className="relative">
            <span
              className={`absolute -left-[31px] flex h-5 w-5 items-center justify-center rounded-full border border-border bg-card ${color}`}
            >
              <Icon className="h-3.5 w-3.5" />
            </span>
            <div className="rounded-lg border border-border bg-card p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{e.source}</span>
                  {e.is_primary_source && (
                    <Badge variant="default" className="gap-1">
                      <ShieldCheck className="h-3 w-3" /> Primary
                    </Badge>
                  )}
                </div>
                <span className="text-xs text-muted-foreground">
                  {timeAgo(e.retrieved_at)}
                </span>
              </div>
              <p className="mt-1.5 text-sm text-foreground/80">{e.summary}</p>
              {e.url && (
                <a
                  href={e.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline"
                >
                  <ArrowUpRight className="h-3 w-3" /> Open citation
                </a>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/* ----------------------------------------------------------------------- */
/* AI Judgment                                                              */
/* ----------------------------------------------------------------------- */
function JudgmentTab({
  signal,
  accentColor,
  barColor,
}: {
  signal: Signal;
  accentColor: string;
  barColor: string;
}) {
  const pct = Math.round((signal.confidence ?? 0) * 100);
  return (
    <div className="space-y-5">
      {/* Confidence meter */}
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-muted-foreground">
            Adjudicator Confidence
          </span>
          <span className={`font-mono text-lg font-semibold ${accentColor}`}>
            {pct}%
          </span>
        </div>
        <Progress value={pct} indicatorClassName={barColor} className="mt-2" />
        <div className="mt-2 flex items-center justify-between">
          <VeracityBadge status={signal.status} />
          <span className="text-xs text-muted-foreground">
            Verdict rendered {timeAgo(signal.updated_at)}
          </span>
        </div>
      </div>

      {/* Reasoning */}
      <div className="rounded-lg border border-border bg-card p-4">
        <h4 className="flex items-center gap-1.5 text-sm font-semibold">
          <Gavel className="h-4 w-4 text-primary" /> Reasoning
        </h4>
        <p className="mt-2 text-sm leading-relaxed text-foreground/85">
          {signal.reasoning || "No reasoning was recorded for this verdict."}
        </p>
      </div>

      {/* Supporting / contradicting */}
      <div className="grid gap-4 sm:grid-cols-2">
        <PointList
          title="Supporting"
          points={signal.key_supporting_points}
          icon={CheckCircle2}
          color="text-[hsl(142_71%_55%)]"
        />
        <PointList
          title="Contradicting"
          points={signal.key_contradicting_points}
          icon={XCircle}
          color="text-[hsl(0_84%_68%)]"
        />
      </div>
    </div>
  );
}

function PointList({
  title,
  points,
  icon: Icon,
  color,
}: {
  title: string;
  points: string[];
  icon: typeof CheckCircle2;
  color: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h4 className="text-sm font-semibold">{title}</h4>
      {points && points.length > 0 ? (
        <ul className="mt-2 space-y-2">
          {points.map((p, i) => (
            <li key={i} className="flex gap-2 text-sm text-foreground/80">
              <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${color}`} />
              <span>{p}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-muted-foreground">None recorded.</p>
      )}
    </div>
  );
}

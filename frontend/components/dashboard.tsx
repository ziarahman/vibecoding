"use client";

/**
 * dashboard.tsx
 * Main IPO Signal Intelligence dashboard: stat cards + enterprise data table.
 *
 * Data flow:
 *   - Stats + signals are fetched from the FastAPI backend via lib/api.
 *   - Veracity filter + sort are SERVER-side (re-query on change).
 *   - Global fuzzy search is CLIENT-side over the current page.
 *   - A manual "Scan" triggers the LangGraph pipeline and refreshes.
 *
 * Handles loading (skeletons), empty, and error states explicitly.
 */

import * as React from "react";
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  BadgeCheck,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Inbox,
  Loader2,
  RefreshCw,
  Search,
  ShieldAlert,
  TrendingUp,
} from "lucide-react";

import { api, ApiError } from "@/lib/api";
import type {
  PaginatedSignals,
  Signal,
  StatsSummary,
  VeracityStatus,
} from "@/lib/types";
import {
  formatPriceRange,
  formatUsd,
  timeAgo,
} from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { VeracityBadge, categoryLabel } from "@/components/veracity";
import { SignalDetailSheet } from "@/components/signal-detail-sheet";

const PAGE_SIZE = 10;

type SortDir = "asc" | "desc";

const STATUS_FILTER_OPTIONS = [
  { label: "All Veracity", value: "" },
  { label: "Verified", value: "VERIFIED" },
  { label: "Speculative", value: "SPECULATIVE" },
  { label: "Contradicted", value: "CONTRADICTED" },
  { label: "Pending", value: "PENDING" },
];

export function Dashboard() {
  // --- data state ---
  const [stats, setStats] = React.useState<StatsSummary | null>(null);
  const [data, setData] = React.useState<PaginatedSignals | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [scanning, setScanning] = React.useState(false);
  const [scanNote, setScanNote] = React.useState<string | null>(null);

  // --- query state (server-side) ---
  const [statusFilter, setStatusFilter] = React.useState<string>("");
  const [sortBy] = React.useState<"discovered_at">("discovered_at");
  const [sortDir, setSortDir] = React.useState<SortDir>("desc");
  const [page, setPage] = React.useState(1);

  // --- client-side fuzzy search ---
  const [search, setSearch] = React.useState("");

  // --- drill-down ---
  const [selected, setSelected] = React.useState<Signal | null>(null);
  const [sheetOpen, setSheetOpen] = React.useState(false);

  const loadStats = React.useCallback(async () => {
    try {
      setStats(await api.getStats());
    } catch {
      /* stats failure is non-fatal; cards show em-dashes */
    }
  }, []);

  const loadSignals = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listSignals({
        status: (statusFilter || undefined) as VeracityStatus | undefined,
        sort_by: sortBy,
        sort_dir: sortDir,
        page,
        page_size: PAGE_SIZE,
      });
      setData(res);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "An unexpected error occurred while loading signals."
      );
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, sortBy, sortDir, page]);

  React.useEffect(() => {
    loadStats();
  }, [loadStats]);

  React.useEffect(() => {
    loadSignals();
  }, [loadSignals]);

  // Reset to page 1 whenever the server filter changes.
  React.useEffect(() => {
    setPage(1);
  }, [statusFilter, sortDir]);

  async function handleScan() {
    setScanning(true);
    setScanNote(null);
    try {
      const result = await api.scan(false);
      setScanNote(
        `Scan complete — ${result.signals_upserted} signals updated in ${result.duration_seconds}s.`
      );
      await Promise.all([loadStats(), loadSignals()]);
    } catch (err) {
      setScanNote(
        err instanceof ApiError ? err.message : "Scan failed unexpectedly."
      );
    } finally {
      setScanning(false);
    }
  }

  function openSignal(signal: Signal) {
    setSelected(signal);
    setSheetOpen(true);
  }

  // Client-side fuzzy filtering over the current page.
  const visibleRows = React.useMemo(() => {
    const items = data?.items ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter((s) => {
      const haystack = [
        s.company_name,
        s.ticker,
        s.exchange,
        s.headline_claim,
        categoryLabel(s.category),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return fuzzyMatch(haystack, q);
    });
  }, [data, search]);

  return (
    <div className="min-h-screen">
      <DashboardHeader
        scanning={scanning}
        onScan={handleScan}
        lastScan={stats?.last_scan_at}
        scanNote={scanNote}
      />

      <main className="mx-auto max-w-screen-2xl space-y-6 px-4 pb-16 sm:px-6 lg:px-8">
        <StatCards stats={stats} loading={!stats && loading} />

        <Card className="overflow-hidden">
          <Toolbar
            search={search}
            onSearch={setSearch}
            statusFilter={statusFilter}
            onStatusFilter={setStatusFilter}
            sortDir={sortDir}
            onToggleSort={() =>
              setSortDir((d) => (d === "desc" ? "asc" : "desc"))
            }
            total={data?.total ?? 0}
            onRefresh={loadSignals}
          />

          <SignalsTable
            loading={loading}
            error={error}
            rows={visibleRows}
            totalForFilter={data?.total ?? 0}
            onRetry={loadSignals}
            onRowClick={openSignal}
            search={search}
          />

          {data && data.total_pages > 1 && (
            <Pagination
              page={data.page}
              totalPages={data.total_pages}
              total={data.total}
              onPrev={() => setPage((p) => Math.max(1, p - 1))}
              onNext={() => setPage((p) => Math.min(data.total_pages, p + 1))}
            />
          )}
        </Card>
      </main>

      <SignalDetailSheet
        signal={selected}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
      />
    </div>
  );
}

/* ----------------------------------------------------------------------- */
/* Header                                                                   */
/* ----------------------------------------------------------------------- */
function DashboardHeader({
  scanning,
  onScan,
  lastScan,
  scanNote,
}: {
  scanning: boolean;
  onScan: () => void;
  lastScan?: string | null;
  scanNote?: string | null;
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-screen-2xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/15 text-primary ring-1 ring-primary/30">
            <TrendingUp className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-semibold leading-tight tracking-tight">
              IPO Signal Intelligence
            </h1>
            <p className="text-xs text-muted-foreground">
              Multi-agent verification of IPO financial signals
              {lastScan ? ` · last scan ${timeAgo(lastScan)}` : ""}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {scanNote && (
            <span className="hidden text-xs text-muted-foreground md:inline">
              {scanNote}
            </span>
          )}
          <Button onClick={onScan} disabled={scanning} className="gap-2">
            {scanning ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Scanning…
              </>
            ) : (
              <>
                <RefreshCw className="h-4 w-4" /> Run Scan
              </>
            )}
          </Button>
        </div>
      </div>
    </header>
  );
}

/* ----------------------------------------------------------------------- */
/* Stat cards                                                               */
/* ----------------------------------------------------------------------- */
function StatCards({
  stats,
  loading,
}: {
  stats: StatsSummary | null;
  loading: boolean;
}) {
  const cards = [
    {
      label: "Total Tracked",
      value: stats?.total_tracked,
      icon: Activity,
      tint: "text-primary",
      ring: "ring-primary/20 bg-primary/10",
    },
    {
      label: "Verified Facts",
      value: stats?.verified,
      icon: BadgeCheck,
      tint: "text-[hsl(142_71%_55%)]",
      ring: "ring-[hsl(142_71%_45%)]/25 bg-[hsl(142_71%_45%)]/10",
    },
    {
      label: "Speculative Noise",
      value: stats?.speculative,
      icon: CircleHelp,
      tint: "text-[hsl(38_92%_60%)]",
      ring: "ring-[hsl(38_92%_50%)]/25 bg-[hsl(38_92%_50%)]/10",
    },
    {
      label: "False / Contradicted",
      value: stats?.contradicted,
      icon: ShieldAlert,
      tint: "text-[hsl(0_84%_68%)]",
      ring: "ring-[hsl(0_84%_60%)]/25 bg-[hsl(0_84%_60%)]/10",
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((c) => {
        const Icon = c.icon;
        return (
          <Card key={c.label} className="relative overflow-hidden">
            <CardContent className="flex items-center gap-4 p-5">
              <div
                className={`flex h-12 w-12 items-center justify-center rounded-xl ring-1 ${c.ring} ${c.tint}`}
              >
                <Icon className="h-6 w-6" />
              </div>
              <div className="min-w-0">
                <p className="truncate text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {c.label}
                </p>
                {loading ? (
                  <Skeleton className="mt-1.5 h-8 w-16" />
                ) : (
                  <p className="mt-0.5 text-3xl font-semibold tabular-nums">
                    {c.value ?? "—"}
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

/* ----------------------------------------------------------------------- */
/* Toolbar                                                                  */
/* ----------------------------------------------------------------------- */
function Toolbar({
  search,
  onSearch,
  statusFilter,
  onStatusFilter,
  sortDir,
  onToggleSort,
  total,
  onRefresh,
}: {
  search: string;
  onSearch: (v: string) => void;
  statusFilter: string;
  onStatusFilter: (v: string) => void;
  sortDir: SortDir;
  onToggleSort: () => void;
  total: number;
  onRefresh: () => void;
}) {
  return (
    <div className="flex flex-col gap-3 border-b border-border p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold">Tracked Signals</h2>
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs tabular-nums text-muted-foreground">
          {total}
        </span>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            placeholder="Search company, ticker…"
            className="w-full pl-8 sm:w-56"
            aria-label="Search signals"
          />
        </div>

        <div className="w-full sm:w-44">
          <Select
            value={statusFilter}
            onChange={(e) => onStatusFilter(e.target.value)}
            options={STATUS_FILTER_OPTIONS}
            aria-label="Filter by veracity status"
          />
        </div>

        <Button
          variant="secondary"
          size="sm"
          onClick={onToggleSort}
          className="gap-1.5"
          title="Sort by discovery date"
        >
          Date
          {sortDir === "desc" ? (
            <ArrowDown className="h-3.5 w-3.5" />
          ) : (
            <ArrowUp className="h-3.5 w-3.5" />
          )}
        </Button>

        <Button
          variant="ghost"
          size="icon"
          onClick={onRefresh}
          title="Refresh"
          aria-label="Refresh signals"
        >
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------------- */
/* Table                                                                    */
/* ----------------------------------------------------------------------- */
function SignalsTable({
  loading,
  error,
  rows,
  totalForFilter,
  onRetry,
  onRowClick,
  search,
}: {
  loading: boolean;
  error: string | null;
  rows: Signal[];
  totalForFilter: number;
  onRetry: () => void;
  onRowClick: (s: Signal) => void;
  search: string;
}) {
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 p-16 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <AlertTriangle className="h-6 w-6" />
        </div>
        <div>
          <p className="font-medium">Couldn’t load signals</p>
          <p className="mt-1 max-w-md text-sm text-muted-foreground">{error}</p>
        </div>
        <Button variant="secondary" size="sm" onClick={onRetry} className="gap-1.5">
          <RefreshCw className="h-4 w-4" /> Retry
        </Button>
      </div>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className="min-w-[220px]">Company</TableHead>
          <TableHead>Category</TableHead>
          <TableHead className="text-right">Valuation</TableHead>
          <TableHead className="text-right">Price Range</TableHead>
          <TableHead>Veracity</TableHead>
          <TableHead className="text-right">Confidence</TableHead>
          <TableHead className="text-right">Discovered</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {loading ? (
          <SkeletonRows />
        ) : rows.length === 0 ? (
          <TableRow className="hover:bg-transparent">
            <TableCell colSpan={7}>
              <EmptyState
                searching={Boolean(search)}
                hasAny={totalForFilter > 0}
              />
            </TableCell>
          </TableRow>
        ) : (
          rows.map((s) => <SignalRow key={s.id} signal={s} onClick={onRowClick} />)
        )}
      </TableBody>
    </Table>
  );
}

function SignalRow({
  signal,
  onClick,
}: {
  signal: Signal;
  onClick: (s: Signal) => void;
}) {
  return (
    <TableRow
      onClick={() => onClick(signal)}
      className="cursor-pointer"
      tabIndex={0}
      role="button"
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick(signal);
        }
      }}
    >
      <TableCell>
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            <span className="font-medium">{signal.company_name}</span>
            {signal.ticker && (
              <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                {signal.ticker}
              </span>
            )}
          </div>
          <span className="line-clamp-1 max-w-md text-xs text-muted-foreground">
            {signal.headline_claim}
          </span>
        </div>
      </TableCell>
      <TableCell>
        <span className="text-sm text-foreground/80">
          {categoryLabel(signal.category)}
        </span>
      </TableCell>
      <TableCell className="text-right font-medium tabular-nums">
        {formatUsd(signal.valuation_usd)}
      </TableCell>
      <TableCell className="text-right tabular-nums text-foreground/80">
        {formatPriceRange(signal.price_range_low, signal.price_range_high)}
      </TableCell>
      <TableCell>
        <VeracityBadge status={signal.status} />
      </TableCell>
      <TableCell className="text-right">
        <ConfidenceCell value={signal.confidence} />
      </TableCell>
      <TableCell className="text-right text-sm text-muted-foreground">
        {timeAgo(signal.discovered_at)}
      </TableCell>
    </TableRow>
  );
}

function ConfidenceCell({ value }: { value: number }) {
  const pct = Math.round((value ?? 0) * 100);
  const color =
    pct >= 75
      ? "bg-[hsl(142_71%_45%)]"
      : pct >= 50
        ? "bg-[hsl(38_92%_50%)]"
        : "bg-[hsl(0_84%_60%)]";
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-muted">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-9 text-right font-mono text-xs tabular-nums text-muted-foreground">
        {pct}%
      </span>
    </div>
  );
}

function SkeletonRows() {
  return (
    <>
      {Array.from({ length: 6 }).map((_, i) => (
        <TableRow key={i} className="hover:bg-transparent">
          <TableCell>
            <Skeleton className="h-4 w-40" />
            <Skeleton className="mt-2 h-3 w-56" />
          </TableCell>
          <TableCell>
            <Skeleton className="h-4 w-20" />
          </TableCell>
          <TableCell>
            <Skeleton className="ml-auto h-4 w-16" />
          </TableCell>
          <TableCell>
            <Skeleton className="ml-auto h-4 w-24" />
          </TableCell>
          <TableCell>
            <Skeleton className="h-5 w-24 rounded-full" />
          </TableCell>
          <TableCell>
            <Skeleton className="ml-auto h-4 w-20" />
          </TableCell>
          <TableCell>
            <Skeleton className="ml-auto h-4 w-14" />
          </TableCell>
        </TableRow>
      ))}
    </>
  );
}

function EmptyState({
  searching,
  hasAny,
}: {
  searching: boolean;
  hasAny: boolean;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Inbox className="h-6 w-6" />
      </div>
      {searching ? (
        <p className="text-sm text-muted-foreground">
          No signals match your search on this page.
        </p>
      ) : hasAny ? (
        <p className="text-sm text-muted-foreground">
          No signals match the current filter.
        </p>
      ) : (
        <div>
          <p className="font-medium">No signals tracked yet</p>
          <p className="mt-1 max-w-sm text-sm text-muted-foreground">
            Run a scan to dispatch the multi-agent pipeline and populate the
            dashboard with discovered IPO signals.
          </p>
        </div>
      )}
    </div>
  );
}

/* ----------------------------------------------------------------------- */
/* Pagination                                                               */
/* ----------------------------------------------------------------------- */
function Pagination({
  page,
  totalPages,
  total,
  onPrev,
  onNext,
}: {
  page: number;
  totalPages: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  return (
    <div className="flex items-center justify-between border-t border-border px-4 py-3">
      <p className="text-xs text-muted-foreground">
        Page <span className="font-medium text-foreground">{page}</span> of{" "}
        {totalPages} · {total} total signals
      </p>
      <div className="flex items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          onClick={onPrev}
          disabled={page <= 1}
          className="gap-1"
        >
          <ChevronLeft className="h-4 w-4" /> Prev
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={onNext}
          disabled={page >= totalPages}
          className="gap-1"
        >
          Next <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------------- */
/* Fuzzy matcher (subsequence + substring) — no external dep                */
/* ----------------------------------------------------------------------- */
function fuzzyMatch(haystack: string, query: string): boolean {
  if (haystack.includes(query)) return true;
  // Subsequence match: every query char appears in order.
  let qi = 0;
  for (let hi = 0; hi < haystack.length && qi < query.length; hi++) {
    if (haystack[hi] === query[qi]) qi++;
  }
  return qi === query.length;
}

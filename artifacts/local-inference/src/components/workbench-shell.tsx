import { Activity, BrainCircuit, ChevronRight, ClipboardCheck, Cpu, Radar } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link, useLocation } from 'wouter';
import { useHealthCheck, getHealthCheckQueryKey } from '@workspace/api-client-react';

type WorkbenchShellProps = {
  children: ReactNode;
};

export function WorkbenchShell({ children }: WorkbenchShellProps) {
  const [location] = useLocation();
  const health = useHealthCheck({ query: { queryKey: getHealthCheckQueryKey(), refetchInterval: 30000 } });
  const isEvaluation = location === '/evaluation';

  return (
    <div className="min-h-[100dvh] bg-background text-foreground">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[278px] flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground lg:flex">
        <div className="flex items-center gap-3 border-b border-sidebar-border px-7 py-7">
          <div className="flex size-11 items-center justify-center rounded-2xl bg-sidebar-primary text-sidebar-primary-foreground shadow-[0_0_0_6px_hsl(75_78%_59%/0.1)]">
            <Radar className="size-6" strokeWidth={2.3} />
          </div>
          <div>
            <div className="font-display text-lg leading-none tracking-tight">Local YOLO</div>
            <div className="mt-1 font-mono-lab text-[10px] uppercase tracking-[0.18em] text-sidebar-foreground/55">Лабораторія інференсу</div>
          </div>
        </div>
        <div className="px-5 pt-9">
          <div className="mb-3 px-3 font-mono-lab text-[10px] uppercase tracking-[0.2em] text-sidebar-foreground/40">Робоча зона</div>
          <nav className="space-y-1.5">
            <Link href="/" data-testid="link-inference" className={`group flex items-center gap-3 rounded-xl px-3 py-3 text-sm transition-colors ${!isEvaluation ? 'bg-sidebar-accent text-sidebar-accent-foreground' : 'text-sidebar-foreground/65 hover:bg-sidebar-accent/70 hover:text-sidebar-foreground'}`}>
              <BrainCircuit className="size-[18px]" />
              <span className="flex-1">Інференс</span>
              {!isEvaluation && <ChevronRight className="size-4 text-sidebar-primary" />}
            </Link>
            <Link href="/evaluation" data-testid="link-evaluation" className={`group flex items-center gap-3 rounded-xl px-3 py-3 text-sm transition-colors ${isEvaluation ? 'bg-sidebar-accent text-sidebar-accent-foreground' : 'text-sidebar-foreground/65 hover:bg-sidebar-accent/70 hover:text-sidebar-foreground'}`}>
              <ClipboardCheck className="size-[18px]" />
              <span className="flex-1">Оцінювання</span>
              {isEvaluation && <ChevronRight className="size-4 text-sidebar-primary" />}
            </Link>
          </nav>
        </div>
        <div className="mt-auto px-5 pb-6">
          <div className="rounded-2xl border border-sidebar-border bg-sidebar-accent/55 p-4">
            <div className="flex items-center gap-2">
              <span className={`size-2 rounded-full ${health.isError ? 'bg-destructive' : health.isLoading ? 'animate-pulse-dot bg-sidebar-primary' : 'bg-sidebar-primary'}`} />
              <span className="font-mono-lab text-[10px] uppercase tracking-[0.16em] text-sidebar-foreground/70">Локальний сервіс</span>
            </div>
            <div className="mt-3 flex items-center justify-between">
              <span className="text-sm text-sidebar-foreground/90">{health.isError ? 'Недоступний' : health.isLoading ? 'Перевірка…' : 'Готовий до роботи'}</span>
              <Activity className="size-4 text-sidebar-primary" />
            </div>
            <div className="mt-3 font-mono-lab text-[10px] text-sidebar-foreground/40">FastAPI · /api/healthz</div>
          </div>
        </div>
      </aside>

      <div className="lg:pl-[278px]">
        <header className="sticky top-0 z-20 flex h-[72px] items-center justify-between border-b border-border/80 bg-background/90 px-5 backdrop-blur-md sm:px-8 lg:px-10">
          <div className="flex items-center gap-2 lg:hidden">
            <div className="flex size-9 items-center justify-center rounded-xl bg-primary text-primary-foreground"><Radar className="size-5" /></div>
            <span className="font-display text-lg">Local YOLO</span>
          </div>
          <div className="hidden items-center gap-2 text-sm text-muted-foreground lg:flex">
            <Cpu className="size-4 text-primary" />
            <span className="font-mono-lab text-[11px] uppercase tracking-[0.15em]">Комп’ютерний зір / локальна лабораторія</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden font-mono-lab text-[10px] uppercase tracking-[0.14em] text-muted-foreground sm:inline">Модельний стенд 01</span>
            <span className="flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground">
              <span className={`size-1.5 rounded-full ${health.isError ? 'bg-destructive' : 'bg-chart-1'}`} />
              {health.isError ? 'Офлайн' : 'Онлайн'}
            </span>
          </div>
        </header>
        <div className="flex items-center gap-2 border-b border-border/60 bg-card/45 px-5 py-3 lg:hidden">
          <Link href="/" data-testid="link-mobile-inference" className={`rounded-lg px-3 py-1.5 text-xs ${!isEvaluation ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'}`}>Інференс</Link>
          <Link href="/evaluation" data-testid="link-mobile-evaluation" className={`rounded-lg px-3 py-1.5 text-xs ${isEvaluation ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'}`}>Оцінювання</Link>
        </div>
        <main>{children}</main>
      </div>
    </div>
  );
}
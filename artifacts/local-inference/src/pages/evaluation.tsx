import { AlertTriangle, CheckCircle2, ClipboardCheck, FileImage, RefreshCw, Target } from 'lucide-react';
import { useGetEvaluationSummary, useListEvaluationExamples, getGetEvaluationSummaryQueryKey, getListEvaluationExamplesQueryKey } from '@workspace/api-client-react';

function LoadingCard() {
  return <div className="h-64 animate-pulse rounded-2xl border border-border bg-card/70"><div className="h-24 rounded-t-2xl bg-muted/70" /><div className="space-y-3 p-5"><div className="h-4 w-2/3 rounded bg-muted" /><div className="h-3 w-4/5 rounded bg-muted" /><div className="h-3 w-1/2 rounded bg-muted" /></div></div>;
}

export default function Evaluation() {
  const examples = useListEvaluationExamples({ query: { queryKey: getListEvaluationExamplesQueryKey() } });
  const summary = useGetEvaluationSummary({ query: { queryKey: getGetEvaluationSummaryQueryKey() } });
  const isLoading = examples.isLoading || summary.isLoading;
  const hasError = examples.isError || summary.isError;

  return (
    <div className="mx-auto max-w-[1500px] px-5 pb-16 pt-8 sm:px-8 lg:px-10 lg:pt-11">
      <section className="animate-rise mb-9 flex flex-col justify-between gap-6 border-b border-border pb-8 md:flex-row md:items-end">
        <div>
          <div className="mb-3 flex items-center gap-2 font-mono-lab text-[10px] uppercase tracking-[0.2em] text-primary"><span className="size-1.5 rounded-full bg-chart-1" />Набір перевірки / 007 кадрів</div>
          <h1 className="font-display max-w-3xl text-[clamp(2.6rem,6vw,5.4rem)] leading-[0.92] tracking-[-0.045em]">Перевірити<br /><span className="text-primary">межі зору.</span></h1>
          <p className="mt-5 max-w-xl text-[15px] leading-7 text-muted-foreground">Сім підготовлених сцен, які показують не тільки влучання, а й характерні помилки моделі.</p>
        </div>
        <div className="flex items-center gap-3 rounded-2xl border border-border bg-card px-4 py-3 shadow-sm">
          <div className="flex size-9 items-center justify-center rounded-xl bg-primary text-primary-foreground"><ClipboardCheck className="size-4" /></div>
          <div><div className="font-mono-lab text-[10px] uppercase tracking-[0.12em] text-muted-foreground">Модель</div><div className="mt-0.5 text-sm font-semibold" data-testid="text-evaluation-model">{summary.data?.model_name ?? 'Завантаження…'}</div></div>
        </div>
      </section>

      {hasError && (
        <div className="mb-6 flex flex-col items-start justify-between gap-4 rounded-2xl border border-destructive/25 bg-destructive/5 p-5 sm:flex-row sm:items-center" role="alert" data-testid="status-evaluation-error">
          <div className="flex items-start gap-3"><AlertTriangle className="mt-0.5 size-5 shrink-0 text-destructive" /><div><div className="font-semibold">Не вдалося завантажити набір оцінювання</div><div className="mt-1 text-sm text-muted-foreground">Перевірте локальний API та повторіть запит.</div></div></div>
          <button type="button" onClick={() => { void examples.refetch(); void summary.refetch(); }} className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-xs font-medium hover:border-primary hover:text-primary" data-testid="button-retry-evaluation"><RefreshCw className="size-3.5" />Повторити</button>
        </div>
      )}

      <section className="mb-8 grid gap-3 sm:grid-cols-3">
        <div className="animate-rise rounded-2xl border border-border bg-card p-5 shadow-sm" style={{ animationDelay: '70ms' }}><div className="mb-4 flex items-center justify-between"><span className="font-mono-lab text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Приклади</span><FileImage className="size-4 text-primary" /></div><div className="text-4xl font-semibold tracking-tight" data-testid="text-total-examples">{summary.data?.total_examples ?? '—'}</div><div className="mt-1 text-xs text-muted-foreground">у повному наборі</div></div>
        <div className="animate-rise rounded-2xl border border-border bg-card p-5 shadow-sm" style={{ animationDelay: '110ms' }}><div className="mb-4 flex items-center justify-between"><span className="font-mono-lab text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Підготовлено</span><CheckCircle2 className="size-4 text-chart-1" /></div><div className="text-4xl font-semibold tracking-tight" data-testid="text-prepared-examples">{summary.data?.prepared_examples ?? '—'}</div><div className="mt-1 text-xs text-muted-foreground">сцен для розбору</div></div>
        <div className="animate-rise rounded-2xl border border-primary/20 bg-primary p-5 text-primary-foreground shadow-[0_12px_30px_hsl(188_56%_28%/0.16)]" style={{ animationDelay: '150ms' }}><div className="mb-4 flex items-center justify-between"><span className="font-mono-lab text-[10px] uppercase tracking-[0.14em] text-primary-foreground/65">Методика</span><Target className="size-4 text-chart-1" /></div><div className="text-sm font-medium leading-6" data-testid="text-evaluation-note">{summary.data?.evaluation_note ?? 'Готуємо опис…'}</div></div>
      </section>

      <div className="mb-5 flex items-center justify-between"><div><div className="font-mono-lab text-[10px] uppercase tracking-[0.18em] text-primary">Картки експериментів</div><h2 className="mt-1 font-display text-2xl">Що очікували — що побачили</h2></div><div className="hidden items-center gap-2 font-mono-lab text-[10px] uppercase tracking-[0.12em] text-muted-foreground sm:flex"><span className="size-1.5 rounded-full bg-chart-1" />живі дані API</div></div>

      {isLoading ? <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">{[0, 1, 2, 3, 4, 5].map((item) => <LoadingCard key={item} />)}</div> : examples.data?.length ? (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {examples.data.map((example, index) => (
            <article key={example.id} className="group animate-rise overflow-hidden rounded-2xl border border-border bg-card shadow-sm transition-transform hover:-translate-y-1 hover:shadow-[0_14px_35px_hsl(188_39%_16%/0.1)]" style={{ animationDelay: `${index * 45}ms` }} data-testid={`card-evaluation-${example.id}`}>
              <div className="relative flex h-24 items-end justify-between overflow-hidden bg-primary px-5 pb-4 text-primary-foreground">
                <div className="absolute -right-3 -top-8 size-32 rounded-full border-[18px] border-chart-1/20 transition-transform group-hover:scale-110" />
                <div className="absolute -right-8 -top-2 size-24 rounded-full border border-chart-1/25" />
                <div><div className="font-mono-lab text-[10px] uppercase tracking-[0.15em] text-primary-foreground/60">Сцена {String(index + 1).padStart(2, '0')}</div><h3 className="mt-1 font-display text-xl">{example.title}</h3></div>
                <span className="font-mono-lab text-[10px] text-primary-foreground/55">{example.filename}</span>
              </div>
              <div className="space-y-5 p-5">
                <div><div className="mb-2 flex items-center gap-2 font-mono-lab text-[10px] uppercase tracking-[0.13em] text-muted-foreground"><Target className="size-3.5 text-primary" />Очікувані об’єкти</div><div className="flex flex-wrap gap-1.5">{example.expected_objects.length ? example.expected_objects.map((object) => <span key={object} className="rounded-md bg-accent/55 px-2 py-1 text-xs text-accent-foreground" data-testid={`tag-expected-${example.id}-${object}`}>{object}</span>) : <span className="text-xs text-muted-foreground">Не вказано</span>}</div></div>
                <div><div className="mb-2 flex items-center gap-2 font-mono-lab text-[10px] uppercase tracking-[0.13em] text-muted-foreground"><AlertTriangle className="size-3.5 text-chart-3" />Спостережені помилки</div>{example.observed_errors.length ? <ul className="space-y-1.5">{example.observed_errors.map((error) => <li key={error} className="flex gap-2 text-xs leading-5 text-foreground/80"><span className="mt-2 size-1 shrink-0 rounded-full bg-chart-3" />{error}</li>)}</ul> : <div className="flex items-center gap-2 text-xs text-chart-2"><CheckCircle2 className="size-3.5" />Помилок не зафіксовано</div>}</div>
                <div className="border-t border-border pt-4 text-xs leading-5 text-muted-foreground"><span className="font-semibold text-foreground">Нотатка: </span>{example.notes}</div>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="flex min-h-64 flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-card/50 text-center" data-testid="empty-evaluation"><ClipboardCheck className="mb-4 size-9 text-muted-foreground/45" /><h3 className="font-display text-2xl">Приклади ще не підготовлені</h3><p className="mt-2 text-sm text-muted-foreground">API повернув порожній набір для оцінювання.</p></div>
      )}
    </div>
  );
}
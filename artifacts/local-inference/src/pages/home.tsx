import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Check, FileImage, Gauge, ImagePlus, LoaderCircle, RotateCcw, ScanLine, SlidersHorizontal, Sparkles, Timer, UploadCloud, X } from 'lucide-react';
import { useRunInference } from '@workspace/api-client-react';
import type { Detection, InferenceResult } from '@workspace/api-client-react';

const MAX_FILE_SIZE = 10 * 1024 * 1024;

function formatConfidence(value: number) {
  return `${Math.round(value * 100)}%`;
}

function formatBytes(value: number) {
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(0)} КБ`;
  return `${(value / (1024 * 1024)).toFixed(1)} МБ`;
}

function DetectionCanvas({ fileUrl, result }: { fileUrl: string; result: InferenceResult }) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-border bg-[#d8ddd2]">
      <img src={fileUrl} alt={`Результат аналізу ${result.filename}`} className="block max-h-[540px] w-full object-contain" data-testid="img-inference-result" />
      {result.detections.map((detection, index) => {
        const left = (detection.box.x1 / result.image_width) * 100;
        const top = (detection.box.y1 / result.image_height) * 100;
        const width = ((detection.box.x2 - detection.box.x1) / result.image_width) * 100;
        const height = ((detection.box.y2 - detection.box.y1) / result.image_height) * 100;
        return (
          <div
            key={`${detection.class_id}-${index}`}
            className="absolute border-2 border-[#b8ed43] bg-[#b8ed43]/10 shadow-[0_0_0_1px_hsl(190_42%_16%/0.3)]"
            style={{ left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%` }}
            data-testid={`box-detection-${index}`}
          >
            <span className="absolute -top-6 left-[-2px] whitespace-nowrap rounded-t-md bg-[#b8ed43] px-2 py-1 font-mono-lab text-[10px] font-bold uppercase text-[#123438]">
              {detection.class_name} · {formatConfidence(detection.confidence)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function PreviewCanvas({ fileUrl, fileName }: { fileUrl: string; fileName: string }) {
  return (
    <div className="relative flex min-h-[300px] items-center justify-center overflow-hidden rounded-2xl border border-dashed border-primary/35 bg-[#e4e7dc] lab-grid sm:min-h-[390px]">
      <img src={fileUrl} alt={`Попередній перегляд ${fileName}`} className="max-h-[460px] w-full object-contain" data-testid="img-file-preview" />
      <div className="pointer-events-none absolute inset-x-5 top-5 flex justify-between font-mono-lab text-[9px] uppercase tracking-[0.16em] text-primary/70">
        <span>ВХІДНИЙ КАДР</span><span>RGB · 8 bit</span>
      </div>
      <div className="pointer-events-none absolute bottom-4 left-4 rounded-md border border-primary/20 bg-card/80 px-2 py-1 font-mono-lab text-[10px] text-muted-foreground backdrop-blur-sm">{fileName}</div>
    </div>
  );
}

function EmptyResult() {
  return (
    <div className="flex min-h-[390px] flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-card/50 px-8 text-center data-stripe" data-testid="empty-inference-result">
      <div className="mb-5 flex size-16 items-center justify-center rounded-[22px] border border-primary/20 bg-primary/5 text-primary">
        <ScanLine className="size-8" strokeWidth={1.4} />
      </div>
      <h3 className="font-display text-2xl text-foreground">Поле спостереження порожнє</h3>
      <p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">Завантажте зображення, щоб побачити, що саме бачить модель. Кожне вікно — реальна відповідь локального сервісу.</p>
      <div className="mt-6 flex items-center gap-2 font-mono-lab text-[10px] uppercase tracking-[0.16em] text-muted-foreground/70"><span className="size-1.5 rounded-full bg-chart-1" />Очікує кадр</div>
    </div>
  );
}

function LoadingResult() {
  return (
    <div className="relative flex min-h-[390px] flex-col items-center justify-center overflow-hidden rounded-2xl border border-primary/20 bg-primary/[0.035] px-8 text-center" data-testid="loading-inference-result">
      <div className="absolute inset-x-8 top-0 h-full overflow-hidden"><div className="animate-scan h-1/5 w-full bg-gradient-to-b from-transparent via-chart-1/35 to-transparent" /></div>
      <LoaderCircle className="relative size-9 animate-spin text-primary" strokeWidth={1.5} />
      <h3 className="relative mt-5 font-display text-2xl">Модель аналізує кадр</h3>
      <p className="relative mt-2 text-sm text-muted-foreground">FastAPI передає зображення в Ultralytics YOLO локально.</p>
      <div className="relative mt-6 flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1.5 font-mono-lab text-[10px] uppercase tracking-[0.12em] text-primary"><span className="size-1.5 animate-pulse-dot rounded-full bg-chart-1" />Виконується інференс</div>
    </div>
  );
}

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [fileUrl, setFileUrl] = useState('');
  const [threshold, setThreshold] = useState(0.35);
  const [result, setResult] = useState<InferenceResult | null>(null);
  const [validationError, setValidationError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const inference = useRunInference();

  useEffect(() => {
    if (!file) {
      setFileUrl('');
      return;
    }
    const url = URL.createObjectURL(file);
    setFileUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const selectedFileMeta = useMemo(() => file ? `${formatBytes(file.size)} · ${file.type.split('/')[1]?.toUpperCase() ?? 'ФАЙЛ'}` : '', [file]);
  const errorMessage = validationError || (inference.isError ? 'Сервіс не повернув результат. Перевірте, чи запущений FastAPI, і спробуйте ще раз.' : '');

  function acceptFile(nextFile?: File) {
    setValidationError('');
    setResult(null);
    if (!nextFile) return;
    if (!nextFile.type.startsWith('image/')) {
      setValidationError('Потрібен файл зображення у форматі JPG, PNG або WEBP.');
      setFile(null);
      return;
    }
    if (nextFile.size > MAX_FILE_SIZE) {
      setValidationError('Файл завеликий. Максимальний розмір — 10 МБ.');
      setFile(null);
      return;
    }
    setFile(nextFile);
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    acceptFile(event.target.files?.[0]);
    event.target.value = '';
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setValidationError('Спочатку додайте зображення для аналізу.');
      return;
    }
    setValidationError('');
    setResult(null);
    inference.mutate({ data: { file, confidence_threshold: threshold } }, { onSuccess: (data) => setResult(data) });
  }

  function resetWorkspace() {
    inference.reset();
    setResult(null);
    setFile(null);
    setValidationError('');
  }

  return (
    <div className="mx-auto max-w-[1500px] px-5 pb-16 pt-8 sm:px-8 lg:px-10 lg:pt-11">
      <section className="animate-rise mb-9 flex flex-col justify-between gap-5 border-b border-border pb-8 md:flex-row md:items-end">
        <div>
          <div className="mb-3 flex items-center gap-2 font-mono-lab text-[10px] uppercase tracking-[0.2em] text-primary"><span className="size-1.5 rounded-full bg-chart-1" />Сесія інференсу / 001</div>
          <h1 className="font-display max-w-3xl text-[clamp(2.6rem,6vw,5.4rem)] leading-[0.92] tracking-[-0.045em] text-foreground">Побачити,<br /><span className="text-primary">як думає модель.</span></h1>
          <p className="mt-5 max-w-xl text-[15px] leading-7 text-muted-foreground">Локальний стенд для дослідження об’єктів, упевненості та помилок YOLO — без прихованої магії, лише вимірюваний результат.</p>
        </div>
        <div className="flex shrink-0 items-center gap-3 rounded-2xl border border-border bg-card px-4 py-3 shadow-sm">
          <div className="flex size-9 items-center justify-center rounded-xl bg-accent text-accent-foreground"><Gauge className="size-4" /></div>
          <div><div className="font-mono-lab text-[10px] uppercase tracking-[0.12em] text-muted-foreground">Поріг упевненості</div><div className="mt-0.5 text-sm font-semibold">{formatConfidence(threshold)} <span className="font-normal text-muted-foreground">налаштовано</span></div></div>
        </div>
      </section>

      <form onSubmit={handleSubmit} className="grid gap-6 xl:grid-cols-[minmax(300px,0.72fr)_minmax(520px,1.28fr)]">
        <div className="animate-rise space-y-5" style={{ animationDelay: '80ms' }}>
          <section className="rounded-2xl border border-border bg-card p-5 shadow-[0_16px_45px_hsl(188_39%_16%/0.06)] sm:p-6">
            <div className="mb-5 flex items-start justify-between">
              <div><div className="mb-1 font-mono-lab text-[10px] uppercase tracking-[0.18em] text-primary">01 / Ввід</div><h2 className="font-display text-2xl">Додайте кадр</h2></div>
              <FileImage className="size-5 text-muted-foreground/60" />
            </div>
            <input ref={inputRef} type="file" accept="image/png,image/jpeg,image/webp" onChange={handleFileChange} className="hidden" data-testid="input-image-file" />
            {!file ? (
              <button type="button" onClick={() => inputRef.current?.click()} className="group flex min-h-[208px] w-full flex-col items-center justify-center rounded-2xl border border-dashed border-primary/35 bg-primary/[0.035] px-5 text-center transition-colors hover:border-primary hover:bg-primary/[0.07]" data-testid="button-select-image">
                <div className="mb-4 flex size-14 items-center justify-center rounded-2xl bg-primary text-primary-foreground transition-transform group-hover:-translate-y-1"><UploadCloud className="size-6" /></div>
                <span className="text-sm font-semibold">Натисніть, щоб вибрати файл</span>
                <span className="mt-2 text-xs text-muted-foreground">JPG, PNG або WEBP · до 10 МБ</span>
              </button>
            ) : (
              <div className="rounded-2xl border border-primary/25 bg-primary/[0.04] p-4" data-testid="selected-file-card">
                <div className="flex items-center gap-3">
                  <div className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-accent text-accent-foreground"><Check className="size-5" /></div>
                  <div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold">{file.name}</div><div className="mt-1 font-mono-lab text-[10px] uppercase tracking-[0.1em] text-muted-foreground">{selectedFileMeta}</div></div>
                  <button type="button" onClick={() => setFile(null)} className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive" aria-label="Видалити файл" data-testid="button-remove-file"><X className="size-4" /></button>
                </div>
                <button type="button" onClick={() => inputRef.current?.click()} className="mt-4 w-full rounded-lg border border-border bg-card px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:border-primary hover:text-primary" data-testid="button-change-file">Замінити зображення</button>
              </div>
            )}
            {errorMessage && <div className="mt-4 flex items-start gap-2 rounded-xl border border-destructive/25 bg-destructive/5 p-3 text-xs leading-5 text-destructive" role="alert" data-testid="status-inference-error"><AlertTriangle className="mt-0.5 size-4 shrink-0" />{errorMessage}</div>}
          </section>

          <section className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6">
            <div className="mb-5 flex items-start justify-between">
              <div><div className="mb-1 font-mono-lab text-[10px] uppercase tracking-[0.18em] text-primary">02 / Параметри</div><h2 className="font-display text-2xl">Налаштуйте сигнал</h2></div>
              <SlidersHorizontal className="size-5 text-muted-foreground/60" />
            </div>
            <label htmlFor="confidence-threshold" className="flex items-center justify-between text-sm font-medium"><span>Мінімальна впевненість</span><span className="rounded-md bg-accent px-2 py-1 font-mono-lab text-xs font-bold text-accent-foreground" data-testid="text-threshold-value">{formatConfidence(threshold)}</span></label>
            <input id="confidence-threshold" type="range" min="0.1" max="0.9" step="0.05" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} className="mt-5 h-2 w-full cursor-pointer accent-primary" data-testid="input-confidence-threshold" />
            <div className="mt-2 flex justify-between font-mono-lab text-[10px] text-muted-foreground"><span>10% · більше знахідок</span><span>90% · суворіше</span></div>
            <div className="mt-5 rounded-xl bg-muted/65 p-3 text-xs leading-5 text-muted-foreground"><Sparkles className="mr-2 inline size-3.5 text-primary" />Значення передається в Python-сервіс разом із файлом. Змініть його, щоб порівняти поведінку моделі.</div>
          </section>

          <button type="submit" disabled={inference.isPending} className="group flex w-full items-center justify-center gap-3 rounded-2xl bg-primary px-5 py-4 text-sm font-semibold text-primary-foreground shadow-[0_10px_24px_hsl(188_56%_28%/0.2)] transition-transform hover:-translate-y-0.5 disabled:cursor-wait disabled:opacity-70" data-testid="button-run-inference">
            {inference.isPending ? <LoaderCircle className="size-5 animate-spin" /> : <ScanLine className="size-5 transition-transform group-hover:rotate-12" />}
            {inference.isPending ? 'Виконується аналіз…' : 'Запустити локальний інференс'}
          </button>
          {(file || result) && !inference.isPending && <button type="button" onClick={resetWorkspace} className="flex w-full items-center justify-center gap-2 text-xs text-muted-foreground transition-colors hover:text-primary" data-testid="button-reset-workspace"><RotateCcw className="size-3.5" />Очистити робочу область</button>}
        </div>

        <div className="animate-rise min-w-0 space-y-5" style={{ animationDelay: '150ms' }}>
          <section className="rounded-2xl border border-border bg-card p-5 shadow-[0_16px_45px_hsl(188_39%_16%/0.06)] sm:p-6">
            <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
              <div><div className="mb-1 font-mono-lab text-[10px] uppercase tracking-[0.18em] text-primary">03 / Спостереження</div><h2 className="font-display text-2xl">Візуальна відповідь</h2></div>
              {result && <div className="flex items-center gap-2 rounded-full bg-accent/50 px-3 py-1.5 font-mono-lab text-[10px] uppercase tracking-[0.1em] text-accent-foreground"><Check className="size-3.5" />Завершено</div>}
            </div>
            {inference.isPending ? <LoadingResult /> : result && fileUrl ? <DetectionCanvas fileUrl={fileUrl} result={result} /> : file && fileUrl ? <PreviewCanvas fileUrl={fileUrl} fileName={file.name} /> : <EmptyResult />}
          </section>

          {result && (
            <section className="animate-rise grid gap-3 sm:grid-cols-3" data-testid="inference-result-summary">
              <div className="rounded-2xl border border-border bg-card p-4"><div className="mb-3 flex items-center gap-2 text-muted-foreground"><ScanLine className="size-4 text-primary" /><span className="font-mono-lab text-[10px] uppercase tracking-[0.12em]">Знахідки</span></div><div className="text-3xl font-semibold tracking-tight" data-testid="text-detection-count">{result.detections.length}</div><div className="mt-1 text-xs text-muted-foreground">об’єктів вище порогу</div></div>
              <div className="rounded-2xl border border-border bg-card p-4"><div className="mb-3 flex items-center gap-2 text-muted-foreground"><Timer className="size-4 text-chart-3" /><span className="font-mono-lab text-[10px] uppercase tracking-[0.12em]">Час</span></div><div className="text-3xl font-semibold tracking-tight" data-testid="text-inference-time">{result.inference_time_ms.toFixed(1)}<span className="ml-1 text-base font-normal text-muted-foreground">мс</span></div><div className="mt-1 text-xs text-muted-foreground">локальний runtime</div></div>
              <div className="rounded-2xl border border-border bg-card p-4"><div className="mb-3 flex items-center gap-2 text-muted-foreground"><FileImage className="size-4 text-chart-4" /><span className="font-mono-lab text-[10px] uppercase tracking-[0.12em]">Розмір</span></div><div className="text-2xl font-semibold tracking-tight" data-testid="text-image-dimensions">{result.image_width} × {result.image_height}</div><div className="mt-1 text-xs text-muted-foreground">пікселів · {result.model_name}</div></div>
            </section>
          )}
        </div>
      </form>

      {result && (
        <section className="animate-rise mt-6 rounded-2xl border border-border bg-card shadow-sm" data-testid="detection-details">
          <div className="flex flex-col justify-between gap-3 border-b border-border px-5 py-5 sm:flex-row sm:items-center sm:px-6">
            <div><div className="font-mono-lab text-[10px] uppercase tracking-[0.18em] text-primary">04 / Вимірювання</div><h2 className="mt-1 font-display text-2xl">Таблиця детекцій</h2></div>
            <div className="flex items-center gap-2 font-mono-lab text-[10px] uppercase tracking-[0.1em] text-muted-foreground"><span className="size-1.5 rounded-full bg-chart-1" />{result.filename}</div>
          </div>
          {result.detections.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[630px] text-left text-sm">
                <thead className="bg-muted/45 font-mono-lab text-[10px] uppercase tracking-[0.12em] text-muted-foreground"><tr><th className="px-6 py-3 font-normal">№</th><th className="px-4 py-3 font-normal">Клас</th><th className="px-4 py-3 font-normal">Впевненість</th><th className="px-4 py-3 font-normal">Координати x1 / y1</th><th className="px-4 py-3 font-normal">Координати x2 / y2</th></tr></thead>
                <tbody>{result.detections.map((detection: Detection, index: number) => <tr key={`${detection.class_id}-${index}`} className="border-t border-border/70 transition-colors hover:bg-muted/30" data-testid={`row-detection-${index}`}><td className="px-6 py-4 font-mono-lab text-xs text-muted-foreground">{String(index + 1).padStart(2, '0')}</td><td className="px-4 py-4 font-semibold">{detection.class_name}<span className="ml-2 font-mono-lab text-[10px] text-muted-foreground">#{detection.class_id}</span></td><td className="px-4 py-4"><span className="rounded-md bg-accent/60 px-2 py-1 font-mono-lab text-xs text-accent-foreground">{formatConfidence(detection.confidence)}</span></td><td className="px-4 py-4 font-mono-lab text-xs text-muted-foreground">{detection.box.x1.toFixed(0)} / {detection.box.y1.toFixed(0)}</td><td className="px-4 py-4 font-mono-lab text-xs text-muted-foreground">{detection.box.x2.toFixed(0)} / {detection.box.y2.toFixed(0)}</td></tr>)}</tbody>
              </table>
            </div>
          ) : <div className="flex items-center gap-3 px-6 py-8 text-sm text-muted-foreground"><AlertTriangle className="size-4 text-chart-3" />Об’єктів вище обраного порогу не знайдено. Це також результат експерименту.</div>}
        </section>
      )}
    </div>
  );
}
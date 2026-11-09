import { useEffect, useRef, useState } from 'react';

import { fetchScene, sceneImageUrl, type Scene } from './api';

function SceneContents({ campaignId, scene }: { campaignId: string; scene: Scene }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = scene.objects.find((object) => object.id === selectedId);
  const [zoom, setZoom] = useState(1);
  const [imageError, setImageError] = useState(false);
  const [imageKey, setImageKey] = useState(0);
  return (
    <>
      <h3>{scene.name}</h3>
      <p>{scene.description}</p>
      {scene.goal && <p>Цель: {scene.goal}</p>}
      <div className="scene__controls">
        <button type="button" onClick={() => setZoom((v) => Math.min(v + 0.5, 3))}>
          Увеличить
        </button>
        <button type="button" onClick={() => setZoom((v) => Math.max(v - 0.5, 1))}>
          Уменьшить
        </button>
        <button type="button" onClick={() => setZoom(1)}>
          Сбросить масштаб
        </button>
      </div>
      {imageError ? (
        <p role="alert">
          Не удалось загрузить изображение.{' '}
          <button
            type="button"
            onClick={() => {
              setImageError(false);
              setImageKey((v) => v + 1);
            }}
          >
            Повторить
          </button>
        </p>
      ) : (
        <div
          className="scene__viewport"
          tabIndex={0}
          aria-label="Изображение сцены: прокрутка при увеличении"
        >
          <div className="scene__image" style={{ width: `${zoom * 100}%` }}>
            <img
              key={imageKey}
              src={sceneImageUrl(campaignId, scene.illustration)}
              alt={scene.name}
              onError={() => setImageError(true)}
            />
            {scene.objects.map((obj) => (
              <button
                key={obj.id}
                type="button"
                className="scene__hotspot"
                aria-label={obj.name}
                style={{
                  left: `${obj.hotspot.x * 100}%`,
                  top: `${obj.hotspot.y * 100}%`,
                  width: `${obj.hotspot.width * 100}%`,
                  height: `${obj.hotspot.height * 100}%`,
                }}
                onClick={() => setSelectedId(obj.id)}
              />
            ))}
          </div>
        </div>
      )}
      <h4>Объекты</h4>
      <ul>
        {scene.objects.map((obj) => (
          <li key={obj.id}>
            <button type="button" onClick={() => setSelectedId(obj.id)}>
              {obj.name}
            </button>
          </li>
        ))}
      </ul>
      {selected && (
        <section aria-label="Описание объекта">
          <h4>{selected.name}</h4>
          <p>{selected.description}</p>
        </section>
      )}
    </>
  );
}

export function SceneViewer({
  campaignId,
  revision = 0,
}: {
  campaignId: string;
  revision?: number;
}) {
  const [scene, setScene] = useState<Scene | null>(null);
  const [status, setStatus] = useState<'loading' | 'waiting' | 'ready' | 'error'>('loading');
  const [retry, setRetry] = useState(0);
  const [open, setOpen] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const result = await fetchScene(campaignId);
        if (!active) return;
        setScene(result.scene);
        setStatus(result.status);
        if (result.status === 'waiting') timer = setTimeout(() => void load(), 3000);
      } catch {
        if (active) setStatus('error');
      }
    }
    void load();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [campaignId, retry, revision]);

  useEffect(() => {
    if (open) dialog.current?.showModal();
    else if (dialog.current?.open) dialog.current.close();
  }, [open]);

  function close() {
    setOpen(false);
    opener.current?.focus();
  }

  return (
    <section className="scene" aria-label="Сцена">
      {status === 'loading' && <p>Загружаем сцену…</p>}
      {status === 'waiting' && <p>Сцена появится после выбора приключения.</p>}
      {status === 'error' && (
        <p role="alert">
          Не удалось загрузить сцену.{' '}
          <button
            type="button"
            onClick={() => {
              setStatus('loading');
              setRetry((v) => v + 1);
            }}
          >
            Повторить
          </button>
        </p>
      )}
      {scene && status === 'ready' && (
        <>
          <div className="scene__desktop">
            <SceneContents campaignId={campaignId} scene={scene} />
          </div>
          <div className="scene__mobile">
            <h3>{scene.name}</h3>
            <p>{scene.description}</p>
            {scene.goal && <p>Цель: {scene.goal}</p>}
            <button ref={opener} type="button" onClick={() => setOpen(true)}>
              Открыть сцену
            </button>
          </div>
          <dialog
            ref={dialog}
            className="scene__dialog"
            aria-label={`Сцена: ${scene.name}`}
            onKeyDown={(event) => {
              if (event.key !== 'Tab') return;
              const focusable = Array.from(
                event.currentTarget.querySelectorAll<HTMLElement>(
                  'button:not([disabled]), [tabindex="0"]',
                ),
              );
              const first = focusable[0];
              const last = focusable[focusable.length - 1];
              if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last?.focus();
              } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first?.focus();
              }
            }}
            onCancel={(event) => {
              event.preventDefault();
              close();
            }}
          >
            <button type="button" onClick={close}>
              Закрыть сцену
            </button>
            {open && <SceneContents campaignId={campaignId} scene={scene} />}
          </dialog>
        </>
      )}
    </section>
  );
}

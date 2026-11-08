import { useEffect, useRef, useState } from 'react';

import { fetchLocationMap, type LocationMapData } from './api';

function MapContents({ map }: { map: LocationMapData }) {
  const [zoom, setZoom] = useState(1);
  // Layout uses only the already-filtered projection. Unknown targets are local,
  // independent stubs per exit, never keyed or grouped by secret destinations.
  const nodes = map.locations.map((location, index) => ({
    ...location,
    x: 120 + index * 220,
    y: 70,
  }));
  const unknown = map.exits.filter((exit) => exit.target_location_id === null);
  const width = Math.max(440, nodes.length * 220 + 20, unknown.length * 220 + 20);
  let stub = 0;
  const lines = map.exits.map((exit) => {
    const source = nodes.find((node) => node.id === exit.source_location_id);
    const destination = nodes.find((node) => node.id === exit.target_location_id);
    const target = destination ?? { x: 120 + stub++ * 220, y: 210 };
    return { source, target, label: exit.label, unknown: !destination };
  });
  return (
    <>
      <p>Текущая · Посещено · Обнаружено · Неизвестная область</p>
      <div className="location-map__controls">
        <button type="button" onClick={() => setZoom((value) => Math.min(value + 0.5, 3))}>
          Увеличить карту
        </button>
        <button type="button" onClick={() => setZoom((value) => Math.max(value - 0.5, 1))}>
          Уменьшить карту
        </button>
        <button type="button" onClick={() => setZoom(1)}>
          Сбросить масштаб карты
        </button>
      </div>
      <div className="location-map__viewport" tabIndex={0} aria-label="Карта: прокрутка">
        <svg
          aria-hidden="true"
          width={width * zoom}
          height={280 * zoom}
          viewBox={`0 0 ${width} 280`}
        >
          {lines.map(
            (line, index) =>
              line.source && (
                <g key={index}>
                  <line
                    x1={line.source.x}
                    y1={line.source.y}
                    x2={line.target.x}
                    y2={line.target.y}
                    stroke="currentColor"
                  />
                  <text
                    x={(line.source.x + line.target.x) / 2}
                    y={(line.source.y + line.target.y) / 2 - 6}
                    textAnchor="middle"
                    fill="currentColor"
                  >
                    {line.label}
                  </text>
                  {line.unknown && (
                    <>
                      <rect
                        x={line.target.x - 85}
                        y={line.target.y - 20}
                        width="170"
                        height="40"
                        rx="8"
                        fill="#3e414c"
                      />
                      <text
                        x={line.target.x}
                        y={line.target.y + 5}
                        textAnchor="middle"
                        fill="white"
                      >
                        Неизвестная область
                      </text>
                    </>
                  )}
                </g>
              ),
          )}
          {nodes.map((node) => (
            <g key={node.id}>
              <rect
                x={node.x - 95}
                y={node.y - 25}
                width="190"
                height="50"
                rx="8"
                fill={node.id === map.current_location_id ? '#38695b' : '#55566e'}
                stroke="white"
                strokeWidth={node.id === map.current_location_id ? 3 : 1}
              />
              <text x={node.x} y={node.y + 5} textAnchor="middle" fill="white">
                {node.name}
              </text>
            </g>
          ))}
        </svg>
      </div>
      <h4>Список карты</h4>
      <ul>
        {map.locations.map((location) => (
          <li key={location.id}>
            {location.name} — {location.id === map.current_location_id ? 'текущая, ' : ''}
            {location.state === 'visited' ? 'посещено' : 'обнаружено'}
          </li>
        ))}
      </ul>
      <h4>Известные выходы</h4>
      <ul>
        {map.exits.map((exit, index) => (
          <li key={index}>
            {map.locations.find((location) => location.id === exit.source_location_id)?.name}:{' '}
            {exit.label} →{' '}
            {map.locations.find((location) => location.id === exit.target_location_id)?.name ??
              'Неизвестная область'}
          </li>
        ))}
      </ul>
    </>
  );
}

export function LocationMap({ campaignId }: { campaignId: string }) {
  const [map, setMap] = useState<LocationMapData | null>(null);
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
        const result = await fetchLocationMap(campaignId);
        if (!active) return;
        setMap(result.map);
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
  }, [campaignId, retry]);

  useEffect(() => {
    if (open) dialog.current?.showModal();
    else if (dialog.current?.open) dialog.current.close();
  }, [open]);

  function close() {
    setOpen(false);
    opener.current?.focus();
  }

  return (
    <section className="location-map" aria-label="Карта">
      <h3>Карта</h3>
      {status === 'loading' && <p>Загружаем карту…</p>}
      {status === 'waiting' && <p>Карта появится после выбора приключения.</p>}
      {status === 'error' && (
        <p role="alert">
          Не удалось загрузить карту.{' '}
          <button
            type="button"
            onClick={() => {
              setStatus('loading');
              setRetry((value) => value + 1);
            }}
          >
            Повторить
          </button>
        </p>
      )}
      {map && status === 'ready' && (
        <>
          <div className="location-map__desktop">
            <MapContents map={map} />
          </div>
          <div className="location-map__mobile">
            <button ref={opener} type="button" onClick={() => setOpen(true)}>
              Открыть карту
            </button>
          </div>
          <dialog
            ref={dialog}
            className="location-map__dialog"
            aria-label="Карта группы"
            onCancel={(event) => {
              event.preventDefault();
              close();
            }}
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
          >
            <button type="button" onClick={close}>
              Закрыть карту
            </button>
            {open && <MapContents map={map} />}
          </dialog>
        </>
      )}
    </section>
  );
}

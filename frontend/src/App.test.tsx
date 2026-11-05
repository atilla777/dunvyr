import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { App } from './App';

describe('App', () => {
  it('renders the application title and skeleton status', () => {
    render(<App />);

    expect(screen.getByRole('heading', { level: 1, name: 'Dunvyr' })).toBeInTheDocument();
    expect(screen.getByText('Frontend-скелет работает')).toBeInTheDocument();
  });
});

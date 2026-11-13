import React from 'react';
import '@testing-library/jest-dom';

// Provide global vi compatibility alias for jest
// @ts-ignore
globalThis.vi = jest;

// Mock next/link globally
jest.mock('next/link', () => {
  return ({ children, href, ...props }: any) => {
    return require('react').createElement('a', { href, ...props }, children);
  };
});

// Mock next/navigation globally
jest.mock('next/navigation', () => {
  const push = jest.fn();
  const replace = jest.fn();
  const back = jest.fn();
  const prefetch = jest.fn();
  return {
    useRouter: () => ({
      push,
      replace,
      back,
      prefetch,
    }),
    usePathname: () => '/dashboard',
    useSearchParams: () => new URLSearchParams(),
  };
});

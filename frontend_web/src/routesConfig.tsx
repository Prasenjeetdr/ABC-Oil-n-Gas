import { PATHS } from '@/constants/path.ts';
import { lazy } from 'react';
import { Navigate } from 'react-router-dom';
import { ChatPage } from './pages/ChatPage';
import { EmptyStatePage } from './pages/EmptyState.tsx';
import { MainLayout } from './pages/MainLayoutWithChatList';

const OAuthCallback = lazy(() => import('./pages/OAuthCallback'));

export const appRoutes = [
  { path: PATHS.OAUTH_CB, element: <OAuthCallback /> },
  {
    element: <MainLayout />,
    children: [
      { path: PATHS.CHAT_EMPTY, element: <EmptyStatePage /> },
      { path: PATHS.CHAT, element: <ChatPage /> },
      { path: '*', element: <Navigate to={PATHS.CHAT_EMPTY} replace /> },
    ],
  },
];

import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import { GatewayProvider } from './context/GatewayContext.tsx';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <GatewayProvider>
      <App />
    </GatewayProvider>
  </StrictMode>,
);

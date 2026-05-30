import React from 'react';
import { HashRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider, theme, App as AntApp } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Processes from './pages/Processes';
import USB from './pages/USB';
import Alerts from './pages/Alerts';
import Settings from './pages/Settings';
import Sandbox from './pages/Sandbox';

const App: React.FC = () => {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#1677ff',
          colorBgContainer: '#141414',
          colorBgLayout: '#0a0a0a',
          colorBorderSecondary: '#303030',
          borderRadius: 6,
        },
      }}
    >
      <AntApp>
        <HashRouter>
          <Routes>
            <Route path="/" element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route path="processes" element={<Processes />} />
              <Route path="usb" element={<USB />} />
              <Route path="alerts" element={<Alerts />} />
              <Route path="sandbox" element={<Sandbox />} />
              <Route path="settings" element={<Settings />} />
            </Route>
          </Routes>
        </HashRouter>
      </AntApp>
    </ConfigProvider>
  );
};

export default App;

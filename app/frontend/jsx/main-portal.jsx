import React, { useState } from 'react';
import ReactDOM from 'react-dom/client';
import Schedule from './Schedule.jsx';
import Payroll from './Payroll.jsx';

const PortalApp = () => {
  const [activeTab, setActiveTab] = useState('schedule');

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-[#3D2517]">Quản lý Lịch ca & Bảng lương</h1>
      </div>

      {/* Tabs */}
      <div className="flex gap-2">
        <button 
          onClick={() => setActiveTab('schedule')} 
          className={`px-4 py-2 rounded font-bold shadow-sm ${activeTab === 'schedule' ? 'bg-[#3D2517] text-white' : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50'}`}
        >
          Lịch làm việc (Ca)
        </button>
        <button 
          onClick={() => setActiveTab('payroll')} 
          className={`px-4 py-2 rounded font-bold shadow-sm ${activeTab === 'payroll' ? 'bg-[#3D2517] text-white' : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50'}`}
        >
          Kỳ tính Lương
        </button>
      </div>

      {/* Render Component tương ứng */}
      {activeTab === 'schedule' ? <Schedule /> : <Payroll />}
    </div>
  );
};

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <PortalApp />
  </React.StrictMode>
);
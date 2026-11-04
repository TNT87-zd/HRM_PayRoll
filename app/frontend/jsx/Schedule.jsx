import React from 'react';

const Schedule = () => {
  return (
    <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
      <div className="flex justify-between items-center mb-4">
        <h2 className="font-bold text-lg text-[#3D2517]">Xếp ca tuần 44 (Cafe 5TN - Đồng Khởi)</h2>
        <button className="bg-[#D9962B] text-white px-4 py-2 rounded text-sm font-bold">🪄 Auto Xếp Ca</button>
      </div>
      <table className="w-full text-sm text-left border">
        <thead className="bg-gray-50 border-b">
          <tr><th className="p-3 border-r w-48">Nhân viên</th><th className="p-3 border-r text-center">T2</th><th className="p-3 border-r text-center">T3</th><th className="p-3 text-center">T4</th></tr>
        </thead>
        <tbody>
          <tr className="border-b">
            <td className="p-3 border-r font-bold">NV0001 (Lê Nam)</td>
            <td className="p-3 border-r"><div className="bg-gray-800 text-white text-xs p-2 text-center rounded border-l-4 border-green-500">CA_SANG<br/>06:30 - 14:30</div></td>
            <td className="p-3 border-r"><div className="bg-gray-800 text-white text-xs p-2 text-center rounded border-l-4 border-green-500">CA_SANG<br/>06:30 - 14:30</div></td>
            <td className="p-3 text-center text-gray-400">Nghỉ (OFF)</td>
          </tr>
          <tr>
            <td className="p-3 border-r font-bold">NV0002 (Mai Lan)</td>
            <td className="p-3 border-r"><div className="bg-orange-100 text-orange-800 text-xs p-2 text-center rounded border border-orange-300">CA_CHIEU<br/>14:30 - 22:30</div></td>
            <td colSpan="2" className="p-3 text-center"><div className="bg-red-100 text-red-600 text-xs p-2 rounded font-bold border border-red-300">⚠ Trùng lịch (CA_CHIEU)</div></td>
          </tr>
        </tbody>
      </table>
    </div>
  );
};

export default Schedule;
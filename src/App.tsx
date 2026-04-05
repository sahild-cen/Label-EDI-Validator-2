import { useState } from 'react';
import Navigation from './components/Navigation';
import CarrierSetup from './pages/CarrierSetup';
import ValidationDashboard from './pages/ValidationDashboard';

function App() {
  const [currentPage, setCurrentPage] = useState<'setup' | 'dashboard'>('setup');

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation currentPage={currentPage} onNavigate={setCurrentPage} />
      {currentPage === 'setup' ? <CarrierSetup /> : <ValidationDashboard />}
    </div>
  );
}

export default App;
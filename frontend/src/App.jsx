import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import Dashboard from './pages/Dashboard.jsx'
import UploadPage from './pages/UploadPage.jsx'
import RecordsPage from './pages/RecordsPage.jsx'
import RecordDetail from './pages/RecordDetail.jsx'
import ValidationPage from './pages/ValidationPage.jsx'
import SearchPage from './pages/SearchPage.jsx'
import ConflictsPage from './pages/ConflictsPage.jsx'
import MapPage from './pages/MapPage.jsx'
import ParcelsPage from './pages/ParcelsPage.jsx'
import ParcelTwinPage from './pages/ParcelTwinPage.jsx'
import NotFound from './pages/NotFound.jsx'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="upload" element={<UploadPage />} />
        <Route path="records" element={<RecordsPage />} />
        <Route path="records/:id" element={<RecordDetail />} />
        <Route path="validation" element={<ValidationPage />} />
        <Route path="conflicts" element={<ConflictsPage />} />
        <Route path="map" element={<MapPage />} />
        <Route path="parcels" element={<ParcelsPage />} />
        <Route path="parcels/record/:id" element={<ParcelTwinPage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}

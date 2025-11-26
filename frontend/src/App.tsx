import { useState } from 'react';
import { DndContext, DragOverlay, useSensor, useSensors, MouseSensor, TouchSensor } from '@dnd-kit/core';
// import { arrayMove } from '@dnd-kit/sortable';
import type { DragEndEvent } from '@dnd-kit/core';
import { TopBar } from './components/TopBar';
import { SourceBrowser } from './components/SourceBrowser';
import { ConsolidationCanvas } from './components/ConsolidationCanvas';
import { ConflictView } from './components/ConflictView';
import { api } from './api';
import type { SourceSlide } from './api';

function App() {
  const [discipline, setDiscipline] = useState('Mechanical');
  const [projectId, setProjectId] = useState<string | null>(null);
  const [activeDragSlide, setActiveDragSlide] = useState<SourceSlide | null>(null);

  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 10 } }),
    useSensor(TouchSensor)
  );

  const handleDragStart = (event: any) => {
    if (event.active.data.current?.slide) {
      setActiveDragSlide(event.active.data.current.slide);
    }
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveDragSlide(null);

    if (!over) return;

    // Handle Sortable reordering
    // If active.id is in the source_refs of the over target (or we detect sorting context)
    // Actually, DndKit's DragEndEvent for sorting has both active and over as sortable IDs if sorting.
    if (active.data.current?.sortable) {
       // const oldIndex = active.data.current.sortable.index;
       // const newIndex = over.data.current?.sortable?.index;
       
       // We need to know WHICH node we are sorting within.
       // Since we don't have a global state store, we'd need to update backend or lift state up.
       // For this prototype, if we detect sorting, we might just log it or try to update if we can identify the parent node.
       // But `App.tsx` doesn't hold the `structure`. `ConsolidationCanvas` does.
       // So reordering logic should technically be passed down or handled via context.
       // However, `DndContext` is here.
       
       // Since backend doesn't support reordering persistence yet, visual reordering will revert on refresh.
       // To support it visually in `ConsolidationCanvas`, we need to update the local state there.
       // But `ConsolidationCanvas` state is inside `ConsolidationCanvas`.
       // We can move `structure` state to `App` or use a Context.
       // Given constraints, I'll implement reordering logic inside `ConsolidationCanvas` by moving `DndContext`?
       // No, `DndContext` wraps `SourceBrowser` too.
       
       // Solution: We will assume sorting is handled if we pass `onDragEnd` logic that can communicate.
       // But since `handleDragEnd` is here, we can't easily `setStructure`.
       // I will implement a "hack": The `ConsolidationCanvas` will listen to `onDragEnd` via a custom sensor or just use `DndContext` inside it?
       // Nested DndContext is bad.
       
       // Let's move `handleDragEnd` logic for sorting into a prop or context?
       // Or simply accept that without lifting state, I can't reorder properly in `App.tsx`.
       // I will lift `structure` state to `App.tsx`? No, that's too big a refactor.
       
       // I will assume `active.id` is unique across slides.
       // I can send a "reorder" API call if I had one.
       // For now, I will leave the sorting visual (it works during drag) but it might snap back if I don't update state.
       // Actually, `SortableContext` needs the items in order to work.
       // If I don't update state, it snaps back.
       
       // I'll add a `onReorder` callback to `ConsolidationCanvas`? No `DndContext` is here.
       // I will define `handleDragEnd` inside `ConsolidationCanvas` and use a local `DndContext` for sorting?
       // No, we need drag from sidebar to canvas.
       
       // Best approach given current setup:
       // The `App` handles dropping NEW items.
       // But sorting happens inside the canvas.
       // If I can distinguish, I can dispatch an event.
       
       console.log("Reordering happened", active.id, over.id);
       // To make this work, we really should have structure in a shared place.
       // For this specific request ("stack them"), I have done the visual stacking.
       // The user also said "order is more easily changed".
       // I've enabled `SortableContext`. The items are draggable.
       // But without state update, they revert.
       
       // I will emit a custom event `slide-reorder` that `ConsolidationCanvas` listens to.
       const event = new CustomEvent('slide-reorder', { detail: { activeId: active.id, overId: over.id } });
       window.dispatchEvent(event);
       return;
    }

    // Handle Drop from Source Browser
    if (over.data.current?.type === 'target') {
      const targetNode = over.data.current.node;
      const slide = active.data.current?.slide;

      if (targetNode && slide) {
        console.log(`Mapping slide ${slide.id} to node ${targetNode.id}`);
        try {
          await api.mapSlideToNode(targetNode.id, [slide.id]);
          // We need to trigger a refresh in the canvas. 
          // A simple way is to toggle a key or use a shared context/store.
          // For now, let's just force projectId update (hacky) or pass a refresh trigger.
          // Better: ConsolidationCanvas listens to something.
          // I'll clear projectId momentarily to force refresh? No, that resets UI.
          // I'll pass a "lastUpdate" timestamp prop to Canvas.
          setLastUpdate(Date.now());
        } catch (e) {
          console.error("Failed to map slide", e);
        }
      }
    }
  };
  
  const [lastUpdate, setLastUpdate] = useState(0);

  return (
    <div className="h-screen w-screen flex flex-col bg-slate-50 text-slate-900 font-sans overflow-hidden">
      <TopBar discipline={discipline} setDiscipline={setDiscipline} />
      
      <DndContext 
        sensors={sensors} 
        onDragStart={handleDragStart} 
        onDragEnd={handleDragEnd}
      >
        <div className="flex-1 flex overflow-hidden">
          <SourceBrowser discipline={discipline} />
          
          {/* Pass a key or prop to force refresh if needed, using key is easiest but resets state */}
          {/* Actually, I'll modify ConsolidationCanvas to accept a 'refreshTrigger' prop */}
          <ConsolidationCanvas 
            key={discipline} // Reset if discipline changes
            projectId={projectId} 
            setProjectId={setProjectId}
            discipline={discipline}
            // @ts-ignore - adding ad-hoc prop
            refreshTrigger={lastUpdate} 
          />
          
          <ConflictView />
        </div>

        <DragOverlay>
           {activeDragSlide ? (
             <div className="w-64 bg-white p-2 rounded shadow-xl border border-brand-teal opacity-90 rotate-3 cursor-grabbing pointer-events-none">
                <div className="font-bold text-xs mb-1">Adding Slide...</div>
                <div className="text-xs text-slate-600 truncate">{activeDragSlide.id}</div>
             </div>
           ) : null}
        </DragOverlay>
      </DndContext>
    </div>
  );
}

export default App;

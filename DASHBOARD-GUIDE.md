# Rivian Dashboard Guide

This guide explains the two dashboard versions available and their features.

## Dashboard Versions

### 1. **rivian-dashboard-stylistic.yaml** (Advanced - Requires Custom Cards) ⭐ Recommended
- Modern, highly stylized design with animations
- Uses Mushroom cards and custom card-mod styling
- Optimized layout with no overlapping elements
- Enhanced visual feedback and state-based colors
- Properly displays all closure states (gear tunnels, tailgate)
- **Best for**: Users with HACS and custom cards installed

**Required Custom Cards:**
- [mushroom](https://github.com/piitaya/lovelace-mushroom) - Modern card designs
- [card-mod](https://github.com/thomasloven/lovelace-card-mod) - Custom CSS styling
- [stack-in-card](https://github.com/custom-cards/stack-in-card) - Card grouping
- [auto-entities](https://github.com/thomasloven/lovelace-auto-entities) - Dynamic entity lists

**Installation:**
1. Install required custom cards via HACS (see above)
2. Copy dashboard YAML to your dashboard configuration
3. Reload Home Assistant UI

### 2. **rivian-dashboard-stylistic-native.yaml** (Native Cards Only)
- Enhanced styling using only native Home Assistant cards
- No custom card dependencies required
- Modern visual effects with CSS animations
- Color-coded status indicators
- Optimized layout with proper spacing
- All closure states properly displayed
- **Best for**: Users who want modern styling without installing custom cards

**Installation:**
1. No custom cards required
2. Copy dashboard YAML to your dashboard configuration
3. Reload Home Assistant UI

## Recent Updates (v1.1)

### ✨ Latest Improvements
- **Fixed overlapping icons** - Reduced status icons from 4→3 on top row and 5→4 on bottom row
- **Better spacing** - Icons now positioned at 20%, 50%, 80% (top) and 12%, 37%, 62%, 88% (bottom)
- **Access control fixes** - All closures now show proper open/closed status
  - Gear tunnels: `binary_sensor.r1t_left_gear_tunnel` and `binary_sensor.r1t_right_gear_tunnel`
  - Tailgate: `binary_sensor.r1t_tailgate`
- **Correct naming** - Changed "Left Bin"/"Right Bin" to "Left Gear Tunnel"/"Right Gear Tunnel"
- **No more "unknown"** - Status displays work correctly for all access controls

### 📐 Optimized Layout
**Top Status Bar** (3 items):
- 🔒 Locked | 🚪 Closed | ⚡ Ready

**Bottom Status Bar** (4 items):
- 🔋 82.2% | ⚙️ Park | 🏁 All-Purpose | 📏 236.7 mi

## Visual Enhancements (Stylistic Versions)

### 🎨 Design Improvements

#### Enhanced Vehicle Display
- **Gradient overlays** on vehicle images for better text readability
- **Drop shadows** on all status icons and labels (enhanced 3px-6px blur)
- **Color-coded battery indicators** with cyan/blue accent color (`#88F1FF`)
- **Hover effects** on interactive elements
- **Rounded corners** (20px) for modern card appearance
- **Elevated shadows** for depth and hierarchy
- **No overlapping elements** - Clean, professional appearance
- **White-space management** - Prevents text wrapping with `white-space: nowrap`

#### Charging Animation
- **Pulsing glow effect** around vehicle image when charging
- **Animated battery icon** with color transitions
- **Enhanced cyan color scheme** for charging-related elements
- **Visual feedback** distinguishing charging vs not charging states

#### Status Cards
- **Color-themed backgrounds** for different sensor types:
  - Green gradient for battery/power
  - Blue gradient for range
  - Orange gradient for speed
  - Grey gradient for odometer
- **Hover animations** with lift effect (translateY)
- **Glowing shadows** on hover

#### Section Headers
- **Gradient backgrounds** with emoji icons
- **Color-coded by function**:
  - Blue: Quick Controls
  - Green: Charging
  - Purple: Access
  - Orange: Seat Climate

### 📱 Layout Improvements

#### Grid-Based Design
- **70/30 split** layout (vehicle display vs controls)
- **Responsive columns** for better mobile experience
- **Organized sections** with clear visual hierarchy
- **Consistent spacing** and padding throughout

#### Card Organization
```
┌─────────────────────────────────┬──────────────┐
│  Vehicle Image with Status      │ Quick        │
│  - Top: Lock, Closed, Ready     │ Controls     │
│  - Bottom: Batt, Gear, Mode, Rng│              │
├─────────────────────────────────┤              │
│  Climate Control                │ Charging     │
├─────────────────────────────────┤ Controls     │
│  Quick Stats (4 buttons)        │              │
│  Battery | Range | ODO | Speed  │ Access       │
└─────────────────────────────────┤ Controls     │
                                  │ - Hood       │
                                  │ - Windows    │
                                  │ - Gear Tunnels│
                                  │              │
                                  │ Seat         │
                                  │ Climate      │
                                  └──────────────┘
```

**Optimizations**:
- Removed overlapping elements (Location tracker, In-use state)
- Cleaner 3+4 icon layout instead of 4+5
- Better horizontal spacing prevents text overflow
- All access controls now show proper status

### 🎬 Animations & Interactions

#### Charging Animations
```css
/* Pulsing battery icon when charging */
@keyframes charging-pulse {
  0%, 100% { opacity: 1; transform: scale(1.5); }
  50% { opacity: 0.7; transform: scale(1.6); }
}

/* Glowing box shadow on vehicle image */
@keyframes charging-glow {
  0%, 100% { box-shadow: 0 8px 32px rgba(136, 241, 255, 0.3); }
  50% { box-shadow: 0 12px 48px rgba(136, 241, 255, 0.6); }
}
```

#### Hover Effects
```css
/* Lift and glow on hover */
ha-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(var(--rgb-color), 0.3);
}
```

### 🎯 Tab Structure

1. **Overview** - Main vehicle display and controls
2. **Tires** - Tire pressure monitoring with color-coded alerts
3. **Software** - OTA updates and download progress
4. **Location** - Map with 24-hour tracking
5. **History** - Activity logs and graphs

## Color Palette

### Primary Colors
- **Cyan/Blue** (`#88F1FF`) - Battery, range, charging indicators
- **Green** - Battery health, positive states
- **Orange** - Speed, warnings
- **Red** - Alerts, low tire pressure
- **Purple** - Access controls
- **Grey** - Neutral information

### Gradients
- **Dark gradients** for overlays: `rgba(0,0,0,0.8)` to transparent
- **Charging gradient**: Blue tint `rgba(0,136,204,0.6)`
- **Card backgrounds**: Subtle color-specific gradients at 5-10% opacity

## Typography

- **Font Weight**:
  - 600-700 for labels
  - 800 for important metrics (battery, range)
- **Text Shadows**: `0 2px 8px rgba(0,0,0,0.9)` for readability
- **Letter Spacing**: `0.5px` for improved legibility
- **Font Sizes**:
  - 13px for status labels
  - 14-15px for metrics
  - 16px for emphasized values

## Installation

### For rivian-dashboard-stylistic.yaml
1. Install required custom cards via HACS:
   ```
   HACS → Frontend → Search:
   - Mushroom
   - Card Mod
   - Stack In Card
   - Auto Entities
   ```
2. Copy dashboard YAML to your dashboard configuration
3. Reload Home Assistant UI

### For rivian-dashboard-stylistic-native.yaml
1. No custom cards required
2. Copy dashboard YAML to your dashboard configuration
3. Reload Home Assistant UI

## Customization Tips

### Change Accent Colors
Find and replace color codes:
- `#88F1FF` - Main cyan accent
- Gradient colors in `rgba()` format

### Adjust Animation Speed
Look for animation properties:
```css
animation: name 2s ease-in-out infinite;
           /* ^^ Change duration here */
```

### Modify Layout Split
In grid layouts, change:
```yaml
grid-template-columns: 70% 30%  # Adjust percentages
```

### Add More Quick Stats
Duplicate button cards in the 4-column grid and add your preferred entities.

## Conditional Display Logic

### Charging vs Not Charging
The dashboard automatically switches between:
- Normal vehicle image when `sensor.r1t_charger_status != 'connected'`
- Charging vehicle image when `sensor.r1t_charger_status == 'connected'`

### Active Charging Animation
Battery icon animates only when `sensor.r1t_charging_state == 'charging'`

## Performance Notes

- **card-mod** CSS is processed client-side; may impact older devices
- Animations use CSS transforms for GPU acceleration
- Conditional cards prevent rendering both views simultaneously
- History graphs limited to reasonable timeframes (1h, 12h, 24h)

## Troubleshooting

### Custom cards not loading
1. Clear browser cache (Ctrl+Shift+R / Cmd+Shift+R)
2. Verify HACS installation
3. Check browser console for errors

### Styling not appearing
1. Ensure card-mod is installed and loaded
2. Check for YAML syntax errors
3. Try the native version if issues persist

### Entity not found errors
1. Verify entity IDs match your vehicle name
2. Check if integration is loaded
3. Replace `r1t_` prefix with your vehicle's prefix

## Migration from Old Dashboard

Your original dashboard entities have been updated:

### Sensor Renames

| Old Entity | New Entity |
|-----------|-----------|
| `sensor.r1t_tire_pressure_front_left_2` | `sensor.r1t_front_left_tire_pressure` |
| `sensor.r1t_tire_pressure_front_right_2` | `sensor.r1t_front_right_tire_pressure` |
| `sensor.r1t_tire_pressure_rear_left_2` | `sensor.r1t_rear_left_tire_pressure` |
| `sensor.r1t_tire_pressure_rear_right_2` | `sensor.r1t_rear_right_tire_pressure` |
| `sensor.r1t_driver_temperature` | `sensor.r1t_cabin_climate_setpoint` |
| `sensor.r1t_cabin_temperature` | `sensor.r1t_cabin_interior_temperature` |
| `sensor.r1t_software_ota_download_progress` | `sensor.r1t_ota_download_progress` |
| `binary_sensor.r1t_charging_status` | `sensor.r1t_charging_state` |
| `binary_sensor.r1t_cabin_climate_preconditioning` | `sensor.r1t_cabin_climate_preconditioning_status` |
| `binary_sensor.r1t_charger_connection` | `sensor.r1t_charger_status` |

### Access Controls (New Feature)

Closures now display proper status (open/closed) instead of just buttons:

| Display Entity | Control Button | Notes |
|---------------|----------------|-------|
| `binary_sensor.r1t_left_gear_tunnel` | `button.r1t_open_gear_tunnel_left` | Shows open/closed |
| `binary_sensor.r1t_right_gear_tunnel` | `button.r1t_open_gear_tunnel_right` | Shows open/closed |
| `binary_sensor.r1t_tailgate` | `button.r1t_drop_tailgate` | Shows open/closed |

**How it works**:
- The card displays the binary sensor state (open/closed)
- Tapping the card triggers the button to open/drop the closure
- No more "unknown" status - you'll see the actual state
- Covers (hood, windows, charge port) already have proper state display built-in

### State Changes

Conditions also changed for enum sensors:
- **Old**: `state: 'on'` / `state: 'off'`
- **New**: `state: 'charging'` / `state: 'connected'` / etc.

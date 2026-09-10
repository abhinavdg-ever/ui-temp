# Rotation / Orientation

Output format (from imaging pipeline):

```csv
folder,filename,rotation_deg,tilt_angle_deg,mirrored
52743839_44976074,1.jpg,0.0,0.5,false
```

| Column | Imaging UI field |
|--------|------------------|
| `folder` | chart / folder name |
| `filename` | page file |
| `rotation_deg` | Orientation Angle (Page) |
| `tilt_angle_deg` | Tilt Angle (Text) |
| `mirrored` | Mirrored (Text) |

Confidence can be added later.

## Layout

```
02-imaging-pipeline/rotation-orientation/
  output/rotation.csv          ← combined (preferred)
  # or drop files under output/ and name them freely
```

Also supported per chart:

`05-imaging-ui/data/folders/<chart>/imaging/<chart>_rotation.csv`

## Frontend

`DATA_MODE=local` overlays these values onto Imaging → **Page Quality & Orientation**.
No dummy values — fields stay blank (`—`) until a CSV row exists.

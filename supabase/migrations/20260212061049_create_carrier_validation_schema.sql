/*
  # Carrier Validation System Schema

  1. New Tables
    - `carriers`
      - `id` (uuid, primary key)
      - `name` (text, unique) - Carrier name (e.g., "DHL", "UPS")
      - `created_at` (timestamptz)
      - `updated_at` (timestamptz)
    
    - `carrier_specs`
      - `id` (uuid, primary key)
      - `carrier_id` (uuid, foreign key to carriers)
      - `label_rules` (jsonb) - Label validation rules template
      - `edi_rules` (jsonb) - EDI validation rules template
      - `label_spec_url` (text) - URL to uploaded label spec PDF
      - `edi_spec_url` (text) - URL to uploaded EDI spec PDF
      - `created_at` (timestamptz)
      - `updated_at` (timestamptz)
    
    - `validation_results`
      - `id` (uuid, primary key)
      - `carrier_id` (uuid, foreign key to carriers)
      - `validation_type` (text) - "label" or "edi"
      - `status` (text) - "PASS" or "FAIL"
      - `errors` (jsonb) - Array of error objects
      - `corrected_script` (text) - Corrected ZPL or EDI script
      - `original_file_url` (text) - URL to uploaded file
      - `created_at` (timestamptz)

  2. Security
    - Enable RLS on all tables
    - Add policies for authenticated users to manage their data
*/

CREATE TABLE IF NOT EXISTS carriers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text UNIQUE NOT NULL,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS carrier_specs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  carrier_id uuid NOT NULL REFERENCES carriers(id) ON DELETE CASCADE,
  label_rules jsonb DEFAULT '{}'::jsonb,
  edi_rules jsonb DEFAULT '{}'::jsonb,
  label_spec_url text,
  edi_spec_url text,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  UNIQUE(carrier_id)
);

CREATE TABLE IF NOT EXISTS validation_results (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  carrier_id uuid NOT NULL REFERENCES carriers(id) ON DELETE CASCADE,
  validation_type text NOT NULL CHECK (validation_type IN ('label', 'edi')),
  status text NOT NULL CHECK (status IN ('PASS', 'FAIL')),
  errors jsonb DEFAULT '[]'::jsonb,
  corrected_script text,
  original_file_url text,
  created_at timestamptz DEFAULT now()
);

ALTER TABLE carriers ENABLE ROW LEVEL SECURITY;
ALTER TABLE carrier_specs ENABLE ROW LEVEL SECURITY;
ALTER TABLE validation_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read carriers"
  ON carriers FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "Anyone can insert carriers"
  ON carriers FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "Anyone can update carriers"
  ON carriers FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Anyone can delete carriers"
  ON carriers FOR DELETE
  TO authenticated
  USING (true);

CREATE POLICY "Anyone can read carrier_specs"
  ON carrier_specs FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "Anyone can insert carrier_specs"
  ON carrier_specs FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "Anyone can update carrier_specs"
  ON carrier_specs FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Anyone can delete carrier_specs"
  ON carrier_specs FOR DELETE
  TO authenticated
  USING (true);

CREATE POLICY "Anyone can read validation_results"
  ON validation_results FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "Anyone can insert validation_results"
  ON validation_results FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "Anyone can update validation_results"
  ON validation_results FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Anyone can delete validation_results"
  ON validation_results FOR DELETE
  TO authenticated
  USING (true);

CREATE INDEX IF NOT EXISTS idx_carrier_specs_carrier_id ON carrier_specs(carrier_id);
CREATE INDEX IF NOT EXISTS idx_validation_results_carrier_id ON validation_results(carrier_id);
CREATE INDEX IF NOT EXISTS idx_validation_results_created_at ON validation_results(created_at DESC);
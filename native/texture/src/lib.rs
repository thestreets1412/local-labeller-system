use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

/// Preserve the exact Python double division followed by float32 rounding.
#[pyfunction]
fn rgba_to_float<'py>(py: Python<'py>, pixels: &[u8]) -> PyResult<Bound<'py, PyBytes>> {
    if !pixels.len().is_multiple_of(4) || pixels.len() > 2048 * 2048 * 4 {
        return Err(PyValueError::new_err(
            "Expected RGBA bytes up to 2048 x 2048 pixels.",
        ));
    }
    let output = py.detach(|| {
        let mut table = [[0u8; 4]; 256];
        for (value, slot) in table.iter_mut().enumerate() {
            *slot = ((value as f64 / 255.0) as f32).to_ne_bytes();
        }
        let mut output = Vec::with_capacity(pixels.len() * 4);
        for &value in pixels {
            output.extend_from_slice(&table[value as usize]);
        }
        output
    });
    Ok(PyBytes::new(py, &output))
}

#[pymodule]
fn visionlabel_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(rgba_to_float, m)?)?;
    Ok(())
}

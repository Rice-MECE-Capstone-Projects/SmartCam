SmartCam Fall 2026 Midterm Report - VLA-only review snapshot

Files:
- SmartCam_VLA_Only_Review.pdf: complete Overleaf-compiled review PDF, 5 pages including references.
- SmartCam_VLA_Only_Source.zip: complete Overleaf project snapshot, including main.tex, references.bib and all figures.
- VLA_Methods.tex: revised Section II-D.
- VLA_Offline_Evaluation.tex: independent Results subsection following the RL results.
- VLA_Only_Changes.diff: exact diff against the source downloaded immediately before this edit.

Rebuild:
Extract SmartCam_VLA_Only_Source.zip into an empty folder and compile main.tex using pdfLaTeX with BibTeX (IEEEtran and standard TeX Live packages required).
Example: latexmk -pdf main.tex
Alternative: pdflatex main.tex; bibtex main; pdflatex main.tex; pdflatex main.tex
The complete project was compiled in the team's Overleaf environment with zero errors.

Scope:
Only the VLA Methods block, new VLA Offline Evaluation Results block and its figure caption changed. After excluding these two blocks, main.tex is identical to the pre-edit version. All .bib and image files in the exported project are byte-identical to the pre-edit files. Existing team source files in this repository are not overwritten by this snapshot.

Evidence:
One partial teacher episode, 340 frames at 10 Hz; SmolVLA 100 BF16 steps, batch 1, frozen vision encoder on RTX 3070 8GB. Nine frames from the same training episode: linear MAE 0.0141 m/s; angular MAE 0.0281 rad/s. These are in-sample offline action imitation results, not evidence of successful closed-loop VLA navigation, generalization, or physical deployment.

Status:
For user/team review. Not submitted to Canvas. Five pages satisfy the upper bound; the exactly-three-page target has not been reached. No team text or figures were reduced to force that target.
